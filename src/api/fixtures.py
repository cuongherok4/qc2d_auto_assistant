"""Clearly synthetic UI/CVAT fixtures, generated locally and never committed as data."""

from __future__ import annotations

import json
import shlex
import tempfile
from pathlib import Path

import pandas as pd

from src import config, contracts
from src.data import bdd100k
from src.features import geometric
from src.scoring import rule


def prepare(out: Path | None = None) -> dict:
    from PIL import Image, ImageDraw

    folder = out or config.ROOT / config.load("review")["fixture_dir"]
    folder.mkdir(parents=True, exist_ok=True)
    images_dir = folder / "images"
    images_dir.mkdir(exist_ok=True)
    frames = bdd100k.read_frames(config.ROOT / "tests/fixtures/det_mini.json")
    objects, images = bdd100k.to_tables(frames)
    preds, evidence = [], []
    for frame in frames:
        image_id = Path(frame["name"]).stem
        image = Image.new("RGB", (contracts.IMG_W, contracts.IMG_H), (65, 83, 101))
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 350, contracts.IMG_W, contracts.IMG_H), fill=(90, 90, 90))
        draw.text((30, 30), "SYNTHETIC FIXTURE - NOT BDD100K / NOT REAL QC", fill="white", font_size=28)
        boxes = []
        for row in objects[objects.image_id == image_id].to_dict("records"):
            box = [row[key] for key in ("x1", "y1", "x2", "y2")]
            draw.rectangle(box, outline="#f4bc42", width=4)
            draw.text((box[0], box[1]), row["category"], fill="white", font_size=20)
            preds.append([image_id, *box, row["category"], 0.9])
            boxes.append(
                {
                    "obj_id": row["obj_id"],
                    "box": box,
                    "note": "Box fixture kiểm UI; không phải kết luận QC",
                    "signal": "fixture",
                }
            )
        image.save(images_dir / f"{image_id}.jpg")
        evidence.append({"image_id": image_id, "boxes": boxes})
    labels = folder / "labels.json"
    labels.write_text(json.dumps(frames, ensure_ascii=False, indent=2), encoding="utf-8")
    predictions = folder / "yolo_preds.parquet"
    pd.DataFrame(preds, columns=contracts.PRED_COLS).to_parquet(predictions, index=False)
    queue = rule.rank(
        {"hard_condition": geometric.hard_condition(objects, images)},
        {"hard_condition": config.load("weights")["signals"]["hard_condition"]},
        "fixture-review-v1",
    )
    queue_path = folder / "ranked_queue_fixture-review-v1.csv"
    queue.to_csv(queue_path, index=False)
    evidence_path = folder / "evidence_fixture-review-v1.jsonl"
    evidence_path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in evidence), encoding="utf-8"
    )
    env = folder / "demo.env"
    env.write_text(
        "\n".join(
            f"export M13_{key}={shlex.quote(str(value))}"
            for key, value in {
                "IMAGES": images_dir.resolve(),
                "PREDICTIONS": predictions.resolve(),
                "QUEUE_FILE": queue_path.resolve(),
                "EVIDENCE_FILE": evidence_path.resolve(),
                "MAPPING": (folder / "cvat_map.parquet").resolve(),
                "DATABASE": (folder / "review.db").resolve(),
            }.items()
        )
        + "\n",
        encoding="utf-8",
    )
    return {
        "fixture": True,
        "images": len(images),
        "queue": str(queue_path),
        "environment": str(env),
        "note": "Queue dùng hard_condition; predictions/box chỉ là fixture, chưa có detector/QC thật",
    }


def prepare_scored(out: Path, *, cvat_url: str | None = None) -> dict:
    """Reproducible real-rule demo on synthetic images, with no invented predictions."""
    from PIL import Image, ImageDraw

    from src import pipeline
    from src.api.review_setup import prepare as prepare_review
    from src.api.saved_labels import atomic_json

    folder = out.resolve()
    version = "rule-fixture-qc-v1"
    marker = folder / "fixture.json"
    if folder.exists():
        if not marker.is_file():
            raise ValueError("Thư mục đã có dữ liệu khác; chọn --out mới, không ghi đè")
        saved = json.loads(marker.read_text())
        if saved.get("kind") != "synthetic_rule_fixture":
            raise ValueError("Không phải fixture QC của công cụ này")
        for name, digest in saved["files"].items():
            path = folder / name
            if not path.resolve().is_relative_to(folder) or pipeline.sha256(path) != digest:
                raise ValueError("Đầu vào fixture đã đổi; giữ nguyên, chọn thư mục mới")
    else:
        folder.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=folder.parent) as temp:
            stage = Path(temp) / "fixture"
            (stage / "images").mkdir(parents=True)
            frames = []
            for number in range(1, 4):
                name = f"fixture-qc-{number:02d}.jpg"
                image = Image.new("RGB", (contracts.IMG_W, contracts.IMG_H), (225, 235, 245))
                draw = ImageDraw.Draw(image)
                draw.rectangle((150, 180, 350, 380), fill=(70, 155, 90), outline="black", width=4)
                draw.text((160, 250), "CAR - FIXTURE", fill="white")
                draw.text((30, 30), "SYNTHETIC FIXTURE - NOT BDD / NO DETECTOR", fill="black")
                image.save(stage / "images" / name)
                frames.append({"name": name, "labels": [{
                    "id": str(number), "category": "car",
                    "box2d": {"x1": 0 if number == 1 else 150, "y1": 180, "x2": 350, "y2": 380},
                    "attributes": {"occluded": False, "truncated": False},
                }]})
            manifest = pipeline.publish(
                frames, stage / "source", version, names=["edge_no_trunc"],
                weights=config.load("weights")["signals"], options=config.load("pipeline"),
                provenance={"kind": "synthetic_rule_fixture", "real_detector": False},
            )
            # Publish immutable inputs atomically, with paths of the final location.
            for key in ("queue", "evidence", "labels", "features", "manifest"):
                manifest[key + "_file"] = pipeline.portable(
                    folder / Path(manifest[key + "_file"]).relative_to(stage)
                )
            atomic_json(stage / "source" / f"ranked_queue_{version}.manifest.json", manifest)
            atomic_json(stage / "fixture.json", {
                "kind": "synthetic_rule_fixture", "files": {
                    str(p.relative_to(stage)): pipeline.sha256(p)
                    for p in stage.rglob("*") if p.is_file()
                },
            })
            stage.rename(folder)
    record = prepare_review(
        folder / "source" / f"ranked_queue_{version}.csv", folder / "images", folder / "review",
        source_root=folder, limit=3, purpose="development", cvat_url=cvat_url,
    )
    return {"fixture": True, "real_detector": False, "scored_qc": True, "images": record["images"],
            "folder": str(folder / "review"), "environment": str(folder / "review" / "runtime.env"),
            "note": "Chỉ rule edge_no_trunc trên ảnh tổng hợp; không kiểm box ôm sát vật thể"}
