"""Prepare isolated review inputs from a verified pipeline snapshot, without rescoring."""

from __future__ import annotations

import json
import re
import shlex
import shutil
import stat
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

import pandas as pd
from PIL import Image

from src import config, contracts, pipeline
from src.api.cvat_import import import_batch
from src.api.cvat_sync import sync
from src.api.operations import package_extension
from src.api.saved_labels import atomic_json
from src.api.schemas import Evidence
from src.api.service import IMAGE_ID
from src.data import bdd100k


def verify(folder):
    record = json.loads((folder / "review.json").read_text())
    for name, digest in record["files"].items():
        path = folder / name
        if not path.resolve().is_relative_to(folder.resolve()) or pipeline.sha256(path) != digest:
            raise ValueError(f"Artifact đã đổi; không ghi đè: {name}")
    return record


def unpack(archive, output):
    """Small Cường bundle only. Image archives stay separate; no replacement extraction."""
    if output.exists():
        raise ValueError("Thư mục giải nén đã có; chọn thư mục mới, không ghi đè")
    with zipfile.ZipFile(archive) as z:
        entries = z.infolist()
        if sum(i.file_size for i in entries) > config.load("review_acceptance")["archive_max_bytes"]:
            raise ValueError("Gói quá lớn cho bundle; giữ ZIP ảnh riêng")
        names = set()
        for i in entries:
            p = PurePosixPath(i.filename)
            if (p.is_absolute() or ".." in p.parts or "\\" in i.filename
                or not p.parts or p.parts[0] not in {"data", "reports"}
                or stat.S_ISLNK(i.external_attr >> 16) or str(p) in names):
                raise ValueError("ZIP chứa đường dẫn không an toàn hoặc trùng")
            names.add(str(p))
            if not i.is_dir() and (p.name.startswith(".") or p.suffix.lower() not in {
                ".json", ".jsonl", ".csv", ".parquet", ".yaml", ".txt", ".md"
            } or "cvat_map" in p.name):
                raise ValueError("Bundle chứa file riêng/credentials hoặc định dạng không hỗ trợ")
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=output.parent) as tmp:
            stage = Path(tmp) / "bundle"
            stage.mkdir()
            z.extractall(stage)
            stage.rename(output)
    return {"folder": str(output.resolve()), "archive_sha256": pipeline.sha256(archive)}


def environment(folder, record, url, *, target=None):
    root = target or folder
    version = record["version"]
    values = {
        "QUEUE_FILE": root / f"ranked_queue_{version}.csv",
        "EVIDENCE_FILE": root / f"evidence_{version}.jsonl",
        "IMAGES": root / "images", "PREDICTIONS": root / "predictions.parquet",
        "MAPPING": root / "cvat_map.parquet", "DATABASE": root / "review.db",
        "SNAPSHOT_DIR": root / "snapshots", "RECHECK_DIR": root / "rechecks",
        "DATA_PURPOSE": record["purpose"], "RECHECK_BACKEND": "src.pipeline:recheck",
        "CVAT_URL": url,
    }
    text = "".join(f"export M13_{k}={shlex.quote(str(v))}\n" for k, v in values.items())
    path = folder / "runtime.env"
    if path.exists() and path.read_text() != text:
        raise ValueError("runtime.env đã đổi; không ghi đè cấu hình")
    if not path.exists():
        path.write_text(text)


def prepare(queue_file, images, output, *, source_root, limit=None, purpose="development",
            original_labels=None, cvat_url=None, role="review"):
    cfg = config.load("review_acceptance")
    limit = limit if limit is not None else cfg["review_images"]
    if limit < 1 or purpose not in {"real", "development"} or role not in {"review", "pilot"}:
        raise ValueError("limit/purpose không hợp lệ")
    root, output, images = source_root.resolve(), output.resolve(), images.resolve()
    source = json.loads(queue_file.with_suffix(".manifest.json").read_text())
    version = source["model_version"]
    if not isinstance(version, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,100}", version):
        raise ValueError("model_version không hợp lệ")
    cvat_url = cvat_url or config.load("paths")["cvat_url"]
    url = urlsplit(cvat_url)
    if url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password:
        raise ValueError("CVAT URL không hợp lệ hoặc chứa credentials")

    def artifact(key):
        path = Path(source[key + "_file"])
        # Published manifests use repo-relative paths; downloaded bundles may use
        # bundle-relative paths. Both must still resolve inside the selected root.
        candidates = {p.resolve() for p in (
            [path] if path.is_absolute() else [root / path, config.ROOT / path]
        ) if p.is_file() and p.resolve().is_relative_to(root)}
        if len(candidates) != 1:
            raise ValueError(f"Artifact nguồn thiếu, mơ hồ hoặc ngoài bundle: {key}")
        path = candidates.pop()
        suffix = {"queue": ".csv", "labels": ".json", "features": ".parquet",
                  "evidence": ".jsonl", "preds": ".parquet"}[key]
        if (path.suffix != suffix or not path.is_relative_to(root)
            or pipeline.sha256(path) != source[key + "_sha256"]):
            raise ValueError(f"Artifact nguồn ngoài bundle hoặc sai hash: {key}")
        return path

    paths = {key: artifact(key) for key in ("queue", "labels", "features", "evidence")}
    if paths["queue"] != queue_file.resolve() or source["method"] != "rule":
        raise ValueError("Cần queue rule đúng manifest để demo và recheck")
    raw_hash = None
    if original_labels is not None and original_labels.suffix == ".json" and original_labels.is_file():
        raw_hash = pipeline.sha256(original_labels)
    if purpose == "real":
        if raw_hash != cfg["labels_sha256"]:
            raise ValueError("Checksum nhãn gốc khác bộ BDD2018 đã chốt; dừng chuẩn bị")
        if "fixture" in source["model_version"].lower() or not source.get("preds_file"):
            raise ValueError("Không dùng fixture/thiếu predictions làm bộ nghiệm thu thật")
    identity = {"source_queue_sha256": source["queue_sha256"],
                "source_labels_sha256": source["labels_sha256"],
                "source_preds_sha256": source.get("preds_sha256"), "limit": limit,
                "purpose": purpose, "original_labels_sha256": raw_hash, "cvat_url": cvat_url, "role": role}
    if output.exists():
        record = verify(output)
        if record["identity"] != identity:
            raise ValueError("Thư mục thuộc batch khác; chọn thư mục mới")
        return record
    frame = pd.read_csv(queue_file, dtype={"image_id": str, "model_version": str}).fillna({"top_reasons": ""})
    if errors := contracts.check_queue(frame):
        raise ValueError("; ".join(errors))
    if set(frame.model_version) != {source["model_version"]} or len(frame) != source["n_images"]:
        raise ValueError("Queue/version/số ảnh không khớp manifest")
    if len(frame) < limit:
        raise ValueError(f"Queue chỉ có {len(frame)} ảnh, không đủ {limit} ảnh yêu cầu")
    source_ids = set(frame.image_id)
    frame = frame.sort_values("rank").head(limit)
    ids = set(frame.image_id)
    if any(not IMAGE_ID.fullmatch(i) or i in {".", ".."} for i in ids):
        raise ValueError("image_id không an toàn")
    frames = bdd100k.read_frames(paths["labels"])
    selected = [f for f in frames if Path(f["name"]).stem in ids]
    if len(selected) != len(ids) or {Path(f["name"]).stem for f in selected} != ids:
        raise ValueError("Nhãn snapshot thiếu hoặc trùng ảnh")
    annotation_kind = "unverified"
    if original_labels is not None and original_labels.is_file() and original_labels.suffix == ".json":
        originals = {Path(f["name"]).stem: f for f in bdd100k.read_frames(original_labels)}
        if not ids <= set(originals):
            raise ValueError("Nhãn gốc thiếu ảnh trong batch")
        annotation_kind = (
            "original" if all(f == originals[Path(f["name"]).stem] for f in selected)
            else "changed_from_original"
        )
    if role == "pilot" and purpose == "real" and annotation_kind != "original":
        raise ValueError("Pilot nhãn gốc cần queue từ đúng nhãn gốc; không dùng snapshot đã tiêm/sửa lỗi")
    rows = [json.loads(s) for s in paths["evidence"].read_text().splitlines() if s.strip()]
    if len(rows) != len({r["image_id"] for r in rows}) or {r["image_id"] for r in rows} != source_ids:
        raise ValueError("Evidence thiếu/trùng/thừa ảnh")
    evidence = [r for r in rows if r["image_id"] in ids]
    for row in evidence:
        for box in row["boxes"]:
            Evidence.model_validate(box)
    features = pd.read_parquet(paths["features"])
    if not features.index.is_unique or set(features.index) != source_ids:
        raise ValueError("Features thiếu/trùng image_id")
    preds = pd.read_parquet(artifact("preds")) if source.get("preds_file") else None
    if preds is not None and (errors := contracts.check_preds(preds)):
        raise ValueError("; ".join(errors))
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent) as tmp:
        stage = Path(tmp) / "prepared"
        (stage / "images").mkdir(parents=True)
        for i in sorted(ids):
            matches = [images / (i + s) for s in (".jpg", ".png", ".jpeg") if (images / (i + s)).is_file()]
            if len(matches) != 1 or not matches[0].resolve().is_relative_to(images):
                raise ValueError(f"Ảnh thiếu/mơ hồ/ngoài images: {i}")
            with Image.open(matches[0]) as image:
                if image.size != (contracts.IMG_W, contracts.IMG_H):
                    raise ValueError(f"Ảnh không đúng 1280×720: {i}")
            shutil.copyfile(matches[0], stage / "images" / matches[0].name)
        queue_name, evidence_name = f"ranked_queue_{version}.csv", f"evidence_{version}.jsonl"
        frame.to_csv(stage / queue_name, index=False)
        (stage / evidence_name).write_text("".join(json.dumps(r, ensure_ascii=False)+"\n" for r in evidence))
        atomic_json(stage / f"labels_{version}.json", selected)
        features.loc[sorted(ids)].to_parquet(stage / f"features_{version}.parquet")
        if preds is not None:
            preds[preds.image_id.isin(ids)].to_parquet(stage / "predictions.parquet", index=False)
        manifest = dict(source)
        for key, name in (("queue", queue_name), ("evidence", evidence_name),
                          ("labels", f"labels_{version}.json"), ("features", f"features_{version}.parquet")):
            manifest[key + "_file"] = pipeline.portable(output / name)
            manifest[key + "_sha256"] = pipeline.sha256(stage / name)
        manifest.update(
            n_images=len(frame),
            manifest_file=pipeline.portable(output / f"ranked_queue_{version}.manifest.json"),
            preds_file=pipeline.portable(output / "predictions.parquet") if preds is not None else None,
            preds_sha256=pipeline.sha256(stage / "predictions.parquet") if preds is not None else None,
            provenance={"kind": "review_subset", **identity, "scores_recomputed": False},
        )
        atomic_json(stage / f"ranked_queue_{version}.manifest.json", manifest)
        package_extension(stage / "extension.zip")
        record = {"identity": identity, "version": version, "purpose": purpose, "images": len(frame),
                  "annotation_kind": annotation_kind,
                  "source_annotation_snapshot": source["labels_sha256"],
                  "files": {str(p.relative_to(stage)): pipeline.sha256(p)
                            for p in stage.rglob("*") if p.is_file()}}
        environment(stage, record, cvat_url, target=output)
        record["files"]["runtime.env"] = pipeline.sha256(stage / "runtime.env")
        atomic_json(stage / "review.json", record)
        stage.rename(output)
    return record


def connect(folder, cvat_url, task_name, *, client=None):
    folder = folder.resolve()
    record = verify(folder)
    if cvat_url != record["identity"]["cvat_url"]:
        raise ValueError("CVAT URL khác cấu hình batch; chuẩn bị batch mới với --url tương ứng")
    version = record["version"]
    if existing := record.get("cvat"):
        if existing["url"] != cvat_url or existing["name"] != task_name:
            raise ValueError("Batch đã gắn task khác; không thay annotations/mapping")
    else:
        if (folder / "cvat_map.parquet").exists() or (folder / "review.db").exists():
            raise ValueError("DB/mapping đã có nhưng chưa đăng ký; không tạo lại task")
        existing = import_batch(cvat_url, folder / f"ranked_queue_{version}.csv", folder / "images",
                                folder / f"labels_{version}.json", task_name, client=client)
        record["cvat"] = {**existing, "url": cvat_url}
        atomic_json(folder / "review.json", record)
    with tempfile.TemporaryDirectory(dir=folder.parent) as tmp:
        mapping = Path(tmp) / "mapping.parquet"
        ids = pd.read_csv(folder / f"ranked_queue_{version}.csv").image_id.tolist()
        count = sync(cvat_url, mapping, task_ids=[existing["task_id"]], image_ids=ids, client=client)
        if count != len(ids):
            raise ValueError("Mapping thiếu ảnh; giữ task mới để kiểm tra")
        target = folder / "cvat_map.parquet"
        if target.exists() and not pd.read_parquet(target).equals(pd.read_parquet(mapping)):
            raise ValueError("Mapping đã đổi; không ghi đè")
        if not target.exists():
            shutil.copyfile(mapping, target)
    return record["cvat"]
