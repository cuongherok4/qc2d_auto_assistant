"""Bước 3b (phần 1) · Chạy detector pretrained COCO -> data/yolo_preds.parquet. Phụ trách: Sơn.
Hướng dẫn: skill `qc-signals` mục b.

Tách khỏi phần so khớp (model_disagreement.py) để đổi detector chỉ phải sửa file này.
Mặc định RT-DETR qua `transformers` (Apache-2.0); model và ngưỡng ở configs/pipeline.yaml mục `detector`.
Đầu ra đúng quy ước 2 (src/contracts.py: PRED_COLS): category đã map COCO -> BDD, toạ độ pixel 1280x720,
conf thấp (0.05) khi lưu. Kiểm bằng: python -m src.cli check --preds data/yolo_preds.parquet

Chạy theo từng phần (`<out>.parts/`): bị ngắt thì chạy lại, ảnh đã xong được bỏ qua.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src import config, contracts


def _part_ids(parts: Path) -> set[str]:
    done = set()
    for f in sorted(parts.glob("part-*.parquet")):
        done |= set(pd.read_parquet(f, columns=["image_id"]).image_id)
    for f in sorted(parts.glob("part-*.empty.json")):
        done |= set(json.loads(f.read_text()))
    return done


def run_detector(images_dir: Path, out_parquet: Path, conf: float | None = None, *, model: str | None = None,
                 revision: str | None = None, batch_size: int | None = None, image_ids=None,
                 device: str | None = None) -> dict:
    import torch
    from PIL import Image
    from transformers import AutoImageProcessor, AutoModelForObjectDetection

    cfg = config.load("pipeline").get("detector", {})
    conf = cfg.get("conf", 0.05) if conf is None else conf
    model = model or cfg["model"]
    revision = revision or cfg.get("revision")
    batch_size = batch_size or cfg.get("batch_size", 4)
    coco_to_bdd = config.load("class_map")["coco_to_bdd"]
    device = device or ("cuda" if torch.cuda.is_available() else "cpu")
    dtype = torch.float16 if device == "cuda" else torch.float32

    images_dir, out_parquet = Path(images_dir), Path(out_parquet)
    ids = sorted(image_ids if image_ids is not None else (p.stem for p in images_dir.glob("*.jpg")))
    if not ids:
        raise ValueError(f"Không có ảnh .jpg trong {images_dir}")
    parts = out_parquet.with_name(out_parquet.name + ".parts")
    parts.mkdir(parents=True, exist_ok=True)
    meta_file = parts / "meta.json"
    meta = {"model": model, "revision": revision, "conf": conf, "class_map": coco_to_bdd}
    if meta_file.exists() and json.loads(meta_file.read_text()) != meta:
        raise ValueError(f"{parts} được tạo với cấu hình khác; xoá thư mục này để chạy lại từ đầu")
    meta_file.write_text(json.dumps(meta, ensure_ascii=False, indent=2))
    todo = [i for i in ids if i not in _part_ids(parts)]

    processor = AutoImageProcessor.from_pretrained(model, revision=revision)
    net = AutoModelForObjectDetection.from_pretrained(model, revision=revision, dtype=dtype).to(device).eval()
    labels = net.config.id2label
    keep = {k: coco_to_bdd[v] for k, v in labels.items() if v in coco_to_bdd}

    chunk = max(batch_size, 200 // batch_size * batch_size)  # ghi một phần mỗi ~200 ảnh
    for start in range(0, len(todo), chunk):
        rows = []
        block = todo[start:start + chunk]
        for b in range(0, len(block), batch_size):
            batch = block[b:b + batch_size]
            pil = [Image.open(images_dir / f"{i}.jpg").convert("RGB") for i in batch]
            sizes = [(im.height, im.width) for im in pil]
            if any(s != (contracts.IMG_H, contracts.IMG_W) for s in sizes):
                raise ValueError(f"Ảnh không phải 1280x720 trong lô {batch}")
            inputs = processor(images=pil, return_tensors="pt").to(device)
            inputs["pixel_values"] = inputs["pixel_values"].to(dtype)
            with torch.inference_mode():
                outputs = net(**inputs)
            results = processor.post_process_object_detection(
                outputs, threshold=conf, target_sizes=torch.tensor(sizes, device=device))
            for image_id, res in zip(batch, results, strict=True):
                for score, label, box in zip(res["scores"].tolist(), res["labels"].tolist(),
                                             res["boxes"].float().tolist(), strict=True):
                    if label not in keep:
                        continue
                    x1, y1 = max(0.0, box[0]), max(0.0, box[1])
                    x2, y2 = min(float(contracts.IMG_W), box[2]), min(float(contracts.IMG_H), box[3])
                    if x2 > x1 and y2 > y1:
                        rows.append((image_id, x1, y1, x2, y2, keep[label], float(score)))
        name = parts / f"part-{block[0]}"  # mỗi ảnh chỉ thuộc một phần nên tên không trùng
        frame = pd.DataFrame(rows, columns=contracts.PRED_COLS)
        if len(frame):
            frame.to_parquet(name.with_suffix(".parquet"), index=False)
        hit = set(frame.image_id)
        empty = [i for i in block if i not in hit]
        if empty:
            name.with_suffix(".empty.json").write_text(json.dumps(empty))
        print(f"detector: {start + len(block)}/{len(todo)} ảnh", flush=True)

    files = sorted(parts.glob("part-*.parquet"))
    preds = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True) if files else \
        pd.DataFrame(columns=contracts.PRED_COLS)
    preds = preds[preds.image_id.isin(set(ids))].sort_values(["image_id", "conf"], ascending=[True, False])
    errors = contracts.check_preds(preds)
    if errors:
        raise ValueError("; ".join(errors))
    preds.to_parquet(out_parquet, index=False)
    summary = {**meta, "n_images": len(ids), "n_preds": len(preds), "device": device,
               "images_without_preds": len(set(ids) - set(preds.image_id))}
    out_parquet.with_suffix(".json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary
