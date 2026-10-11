"""Clearly synthetic UI/CVAT fixtures, generated locally and never committed as data."""

from __future__ import annotations

import json
import shlex
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
