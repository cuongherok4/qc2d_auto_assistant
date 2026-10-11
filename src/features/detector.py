"""Bước 3b (phần 1) · Chạy detector pretrained COCO -> data/yolo_preds.parquet. Phụ trách: Sơn.
Hướng dẫn: skill `qc-signals` mục b.

Tách khỏi phần so khớp (model_disagreement.py) để đổi detector (YOLOv8n / RT-DETR) chỉ phải sửa file này.
Đầu ra đúng quy ước 2 (src/contracts.py: PRED_COLS): category đã map COCO -> BDD, toạ độ pixel 1280x720,
conf thấp (0.05) khi lưu. Kiểm bằng: python -m src.cli check --preds data/yolo_preds.parquet
"""

from __future__ import annotations

from pathlib import Path


def run_detector(images_dir: Path, out_parquet: Path, conf: float = 0.05) -> None:
    raise NotImplementedError("TODO(Sơn): chạy detector, map class qua configs/class_map.yaml: coco_to_bdd")
