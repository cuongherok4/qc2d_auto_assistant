"""Bước 3a · 4 tín hiệu hình học / ngữ cảnh dễ. Phụ trách: Long. Hướng dẫn: skill `qc-signals` mục a.

Làm theo khuôn của `hard_condition` trong geometric.py: (objects, images, cfg) -> Signals,
trả kết quả cho MỌI ảnh trong `images` (ảnh không kích hoạt: value=0, reason="").
Thống kê tính trên chính file nhãn đang chấm (đã tiêm lỗi), không dùng nhãn sạch.
"""

from __future__ import annotations

from src.features.base import Signals


def crowded(objects, images, cfg=None) -> Signals:
    raise NotImplementedError("TODO(Long): số box theo bách phân vị 75–99, ảnh đông dễ sót")


def many_tiny(objects, images, cfg=None) -> Signals:
    raise NotImplementedError("TODO(Long): nhiều box cao < 20px")


def rare_class(objects, images, cfg=None) -> Signals:
    raise NotImplementedError("TODO(Long): ảnh có class chiếm < 1% toàn tập")


def edge_no_trunc(objects, images, cfg=None) -> Signals:
    raise NotImplementedError("TODO(Long): box cách mép < 2px mà truncated=false (geometry.touches_edge)")


SIGNALS = {
    "crowded": crowded,
    "many_tiny": many_tiny,
    "rare_class": rare_class,
    "edge_no_trunc": edge_no_trunc,
}
