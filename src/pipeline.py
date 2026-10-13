"""Rank immutable input snapshots and publish matched queue/evidence/provenance files."""

from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path

import pandas as pd

from src import config, contracts
from src.data import bdd100k
from src.features import geometric, guideline_rules, model_disagreement, simple_signals
from src.scoring import rule


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2,
                                    allow_nan=False)+"\n", encoding="utf-8")


def load_spec(path):
    """Require the source-checked approval produced by Tú Anh's existing tools."""
    from src.guideline.extract import load_approved

    spec = load_approved(Path(path))
    missing = [r["check"] for r in spec["rules"] if r["check"] not in guideline_rules.CHECKS]
    if missing:
        raise ValueError(f"Luật chưa triển khai, không thể coi như đã chạy: {missing}")
    return spec


def compute(frames, *, names, weights, options, preds=None, spec=None):
    objects, images = bdd100k.to_tables(frames)
    ids = set(images.image_id)
    if len(ids) != len(images) or not ids:
        raise ValueError("Batch phải có image_id duy nhất và không rỗng")
    signals = {}
    registry = {**geometric.SIGNALS, **simple_signals.SIGNALS}
    for name in names:
        if name not in registry:
            raise ValueError(f"Tín hiệu chưa đăng ký: {name}")
        try:
            signals[name] = registry[name](objects, images, options.get("signal_options", {}))
        except NotImplementedError as exc:
            raise ValueError(f"Tín hiệu được yêu cầu chưa triển khai: {name}") from exc
    if preds is not None:
        errors = contracts.check_preds(preds)
        if errors:
            raise ValueError("; ".join(errors))
        opts = {**options.get("detector_options", {}), "spec": spec}
        for name, fn in model_disagreement.SIGNALS.items():
            try:
                signals[name] = fn(objects, images, preds, opts)
            except NotImplementedError as exc:
                raise ValueError(f"Cần phần Sơn triển khai trước khi dùng --preds: {name}") from exc
    if spec is not None:
        missing = [r["check"] for r in spec["rules"] if r["check"] not in guideline_rules.CHECKS]
        if missing:
            raise ValueError(f"Luật chưa triển khai: {missing}")
        if not spec.get("approved_by"):
            raise ValueError("Spec chưa được người duyệt")
        signals["guideline"] = guideline_rules.guideline(objects, images, spec)
    if any(set(values) != ids for values in signals.values()):
        raise ValueError("Tín hiệu thiếu hoặc thừa image_id")
    used = {n: s for n, s in signals.items() if weights.get(n, 0) > 0}
    if not used:
        raise ValueError("Không có tín hiệu có trọng số dương")
    features = pd.DataFrame({n: {i: s.value for i, s in values.items()} for n, values in used.items()})
    features.index.name = "image_id"
    return used, features.sort_index(), images


def publish(frames, output_dir, version, *, names=None, weights=None, options=None, preds_file=None,
            spec=None, provenance=None):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,100}", version):
        raise ValueError("version chỉ gồm chữ, số, dấu chấm/gạch")
    options = copy.deepcopy(options if options is not None else config.load("pipeline"))
    weights = copy.deepcopy(weights if weights is not None else config.load("weights")["signals"])
    names = list(names if names is not None else options["signals"])
    preds = pd.read_parquet(preds_file) if preds_file else None
    signals, features, images = compute(frames, names=names, weights=weights, options=options,
                                         preds=preds, spec=spec)
    queue = rule.rank(signals, weights, version, config.load("weights").get("top_reasons", 3))
    output = Path(output_dir).resolve()
    paths = {"queue_file": output/f"ranked_queue_{version}.csv",
             "evidence_file": output/f"evidence_{version}.jsonl",
             "labels_file": output/f"labels_{version}.json",
             "features_file": output/f"features_{version}.parquet",
             "manifest_file": output/f"ranked_queue_{version}.manifest.json"}
    if any(path.exists() for path in paths.values()):
        raise ValueError("Phiên bản đã có artifact; chọn --version mới, không ghi đè hàng đợi")
    output.mkdir(parents=True, exist_ok=True)
    rule.write_evidence(signals, paths["evidence_file"])
    write_json(paths["labels_file"], frames)
    features.to_parquet(paths["features_file"])
    queue_bytes = queue.to_csv(index=False).encode()
    manifest = {"schema_version": 1, "model_version": version, "method": "rule",
                "queue_sha256": hashlib.sha256(queue_bytes).hexdigest(),
                "labels_sha256": sha256(paths["labels_file"]),
                "features_sha256": sha256(paths["features_file"]),
                "evidence_sha256": sha256(paths["evidence_file"]),
                "used_signals": list(signals), "requested_signals": names, "weights": weights,
                "options": options, "spec": spec, "n_images": len(images),
                "preds_file": str(Path(preds_file).resolve()) if preds_file else None,
                "preds_sha256": sha256(preds_file) if preds_file else None,
                "provenance": provenance or {}, **{k: str(v) for k, v in paths.items()}}
    write_json(paths["manifest_file"], manifest)
    # Queue appears last: consumers can never see a new queue with missing evidence.
    temp = paths["queue_file"].with_suffix(".csv.tmp")
    temp.write_bytes(queue_bytes)
    temp.replace(paths["queue_file"])
    return manifest


def recheck(*, snapshot, queue, output_dir, model_version, seed, manifest_file=None):
    """Callable adapter for Tú Anh's RecheckManager; carries earlier saved edits forward."""
    if manifest_file is None:
        from src.api.service import QueueService
        from src.api.settings import Settings
        from src.api.store import ReviewStore

        settings = Settings.configured()
        _, _, active_path = QueueService(settings, ReviewStore(settings.database)).snapshot()
        if active_path is None:
            raise ValueError("Chưa có queue nguồn")
        manifest_file = active_path.with_suffix(".manifest.json")
    manifest = json.loads(Path(manifest_file).read_text(encoding="utf-8"))
    if manifest["method"] != "rule":
        raise ValueError("Adapter này chỉ chấm lại rule, không tự hạ GBM thành rule")
    for kind in ("queue", "labels", "features", "evidence"):
        if sha256(manifest[f"{kind}_file"]) != manifest[f"{kind}_sha256"]:
            raise ValueError(f"Artifact nguồn đã đổi: {kind}")
    original = pd.read_csv(manifest["queue_file"], dtype={"image_id": str, "model_version": str}).fillna("")
    try:
        pd.testing.assert_frame_equal(original.reset_index(drop=True), queue.reset_index(drop=True),
                                      check_dtype=False)
    except AssertionError as exc:
        raise ValueError("Queue đang phục vụ khác queue trong manifest") from exc
    if manifest["preds_file"] and sha256(manifest["preds_file"]) != manifest["preds_sha256"]:
        raise ValueError("Prediction nguồn đã đổi")
    if (snapshot["width"], snapshot["height"]) != (contracts.IMG_W, contracts.IMG_H):
        raise ValueError("Snapshot cần toạ độ ảnh gốc 1280x720")
    frames = json.loads(Path(manifest["labels_file"]).read_text(encoding="utf-8"))
    matches = [fr for fr in frames if fr["name"].removesuffix(".jpg") == snapshot["image_id"]]
    if len(matches) != 1:
        raise ValueError("Snapshot không thuộc tập ảnh nguồn")
    labels = []
    for obj in snapshot["boxes"]:
        points = obj["box"]
        if len(points) != 4 or not 0 <= points[0] < points[2] <= contracts.IMG_W \
                or not 0 <= points[1] < points[3] <= contracts.IMG_H:
            raise ValueError("Snapshot có box không hợp lệ")
        labels.append({"id": obj["obj_id"], "category": obj["category"],
                       "attributes": obj["attributes"],
                       "box2d": dict(zip(("x1", "y1", "x2", "y2"), points, strict=True))})
    matches[0]["labels"] = labels
    return publish(frames, output_dir, model_version, names=manifest["requested_signals"],
                   weights=manifest["weights"], options=manifest["options"],
                   preds_file=manifest["preds_file"], spec=manifest["spec"],
                   provenance={"kind": "saved_cvat_recheck", "seed": seed,
                               "parent_queue_sha256": manifest["queue_sha256"],
                               "image_id": snapshot["image_id"],
                               "annotation_version": snapshot.get("annotation_version")})
