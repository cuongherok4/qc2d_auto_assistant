"""Sinh bảng image_id -> task/job/frame từ CVAT LOCAL của máy đang chạy. Phụ trách: Tú Anh.
Hướng dẫn: skill `review-queue`.

CVAT chạy local trên từng máy nên id task/job/frame khác nhau giữa các máy: KHÔNG commit bảng này.
Gọi REST API của CVAT tại configs/paths.yaml: cvat_url, khớp ảnh theo tên file,
ghi ra configs/paths.yaml: cvat_map (data/cvat_map.parquet, cột image_id, task_id, job_id, frame).
Tài khoản CVAT đọc từ biến môi trường CVAT_USER / CVAT_PASSWORD (.env), không ghi vào code.
"""

from __future__ import annotations

from pathlib import Path


def sync(cvat_url: str, out_parquet: Path) -> int:
    """Trả về số ảnh đã khớp."""
    raise NotImplementedError("TODO(Tú Anh): đọc /api/tasks, /api/jobs của CVAT local, khớp theo tên file")
