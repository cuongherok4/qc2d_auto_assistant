"""Bước 3b (phần 2) · Bất đồng giữa nhãn và detector. Phụ trách: Sơn. Hướng dẫn: skill `qc-signals` mục b.

Đầu vào: bảng objects + data/yolo_preds.parquet. Khớp từng ảnh bằng src.features.geometry.match_boxes.
Bỏ rider, traffic sign (COCO không có). Nếu có spec guideline: lọc dự đoán theo spec trước khi khớp.
Mỗi hàm: (objects, images, preds, cfg) -> Signals.
"""

from __future__ import annotations


def model_missing_label(objects, images, preds, cfg=None):
    raise NotImplementedError("TODO(Sơn): dự đoán conf cao không khớp nhãn nào -> nghi thiếu box")


def model_class_conflict(objects, images, preds, cfg=None):
    raise NotImplementedError("TODO(Sơn): khớp nhưng khác class -> nghi sai class")


def model_loose_box(objects, images, preds, cfg=None):
    raise NotImplementedError("TODO(Sơn): cùng class, 0.5 <= IoU < 0.7 -> nghi box lệch")


def label_unsupported(objects, images, preds, cfg=None):
    raise NotImplementedError("TODO(Sơn): nhãn lớn không có dự đoán nào gần -> nghi box giả")


SIGNALS = {
    "model_missing_label": model_missing_label,
    "model_class_conflict": model_class_conflict,
    "model_loose_box": model_loose_box,
    "label_unsupported": label_unsupported,
}
