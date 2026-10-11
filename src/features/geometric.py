"""Bước 3a · Tín hiệu hình học / ngữ cảnh (phần khó). Phụ trách: Cường. Hướng dẫn: skill `qc-signals` mục a.
4 tín hiệu dễ (crowded, many_tiny, rare_class, edge_no_trunc) nằm ở simple_signals.py (Long).

Mỗi hàm: (objects, images, cfg) -> Signals, trả kết quả cho MỌI ảnh trong `images`.
`hard_condition` đã viết xong làm mẫu: copy khuôn này cho các tín hiệu còn lại.
Thống kê (median, MAD, tần suất class) tính trên chính file nhãn đang chấm, không dùng nhãn sạch.
"""

from __future__ import annotations

import pandas as pd

from src.features.base import SignalResult, Signals

HARD = {"night": "đêm", "rainy": "mưa", "snowy": "tuyết", "foggy": "sương mù"}


def hard_condition(objects: pd.DataFrame, images: pd.DataFrame, cfg: dict | None = None) -> Signals:
    """Ảnh đêm/mưa/tuyết/sương: nhãn dễ sót hơn. Chỉ là ngữ cảnh, value thấp."""
    out = {}
    for row in images.itertuples(index=False):
        hits = [HARD[v] for v in (row.timeofday, row.weather) if v in HARD]
        value = min(1.0, 0.5 * len(hits))
        reason = f"Ảnh {', '.join(hits)}, {row.n_boxes} box" if hits else ""
        out[row.image_id] = SignalResult("hard_condition", value, reason)
    return out


def size_outlier(objects, images, cfg=None) -> Signals:
    raise NotImplementedError("TODO(Cường): z-score robust log diện tích/tỉ lệ theo class")


def dup_same_class(objects, images, cfg=None) -> Signals:
    raise NotImplementedError("TODO(Cường): hai box cùng class IoU > 0.5")


def overlap_cross_class(objects, images, cfg=None) -> Signals:
    raise NotImplementedError("TODO(Cường): hai box khác class IoU > 0.7, trừ rider–bicycle/motorcycle")


SIGNALS = {
    "hard_condition": hard_condition,
    "size_outlier": size_outlier,
    "dup_same_class": dup_same_class,
    "overlap_cross_class": overlap_cross_class,
}
