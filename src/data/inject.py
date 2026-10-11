"""Bước 2 · Tiêm lỗi có đáp án. Phụ trách: Cường. Hướng dẫn: skill `error-injection`.

Đầu vào : det_val.json gốc + configs/injection.yaml
Đầu ra  : data/injected/det_val_injected.json   (cùng định dạng BDD, các bước sau dùng như dữ liệu thật)
          data/injected/injected_errors.json     ({meta, image_order, splits, errors})
"""

from __future__ import annotations


def inject(frames: list[dict], cfg: dict) -> tuple[list[dict], dict]:
    """Trả về (frames_đã_tiêm, đáp_án). Cùng seed phải ra cùng đáp án."""
    raise NotImplementedError("TODO(Cường): tiêm 5 loại lỗi theo skill error-injection")
