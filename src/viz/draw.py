"""Vẽ box lên ảnh để kiểm tay. Phụ trách: Sơn. Hướng dẫn: skill `bdd100k-data` mục "Vẽ box để kiểm tay".

Tô màu theo nguồn: nhãn gốc / dự đoán model / box nghi vấn (từ evidence). Ghi class + chiều cao px
cạnh box. Ảnh xuất ra reports/viz/ (không commit).
"""

from __future__ import annotations

from pathlib import Path


def draw_image(image_id: str, objects, preds=None, evidence=None, out_dir: Path | None = None) -> Path:
    raise NotImplementedError("TODO(Tú Anh): vẽ box bằng PIL.ImageDraw")
