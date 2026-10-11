"""Bước 3c · Rule engine kiểm nhãn theo spec guideline của batch. Phụ trách: Long.
Hướng dẫn: skill `guideline-rules`.

Đọc configs/guidelines/<id>.yaml (đã duyệt, approved_by khác rỗng). Mỗi `check` trong spec là một hàm
đăng ký trong CHECKS. Kết quả: SignalResult name="guideline", reason bắt đầu bằng rule ID:
"[R1] Box car cao 12px, dưới ngưỡng 15px của guideline".
"""

from __future__ import annotations

CHECKS: dict = {}  # "below_min_height": fn, "class_not_allowed": fn, "missing_attribute": fn


def load_spec(guideline_ref: str, allow_unapproved: bool = False) -> dict:
    """guideline_ref dạng "bdd-default@1.0.0". Từ chối spec chưa duyệt trừ khi allow_unapproved."""
    raise NotImplementedError("TODO(Long): đọc spec, kiểm version và approved_by")


def guideline(objects, images, spec: dict):
    raise NotImplementedError("TODO(Long): chạy CHECKS theo spec, value = 1 - prod(1 - severity)")


SIGNALS = {"guideline": guideline}
