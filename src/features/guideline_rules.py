"""Bước 3c · Rule engine kiểm nhãn theo spec guideline của batch. Phụ trách: Long.
Hướng dẫn: skill `guideline-rules`.

Đọc configs/guidelines/<id>.yaml (đã duyệt, approved_by khác rỗng). Mỗi `check` trong spec là một hàm
đăng ký trong CHECKS. Kết quả: SignalResult name="guideline", reason bắt đầu bằng rule ID:
"[R1] Box car cao 12px, dưới ngưỡng 15px của guideline".
"""

from __future__ import annotations

import warnings
from collections import Counter

import yaml

from src import config

CHECKS: dict = {}  # "below_min_height": fn, "class_not_allowed": fn, "missing_attribute": fn

GUIDELINE_DIR = config.CONFIG_DIR / "guidelines"
REQUIRED_KEYS = ("id", "version", "approved_by", "classes", "rules")


class UnapprovedSpecError(ValueError):
    """Spec chưa có người duyệt (approved_by rỗng)."""


def load_spec(guideline_ref: str, allow_unapproved: bool = False) -> dict:
    """guideline_ref dạng "bdd-default@1.0.0". Từ chối spec chưa duyệt trừ khi allow_unapproved."""
    gid, sep, version = guideline_ref.partition("@")
    if not (sep and gid and version):
        raise ValueError(f"guideline_ref phải có dạng <id>@<version>, nhận được {guideline_ref!r}")
    path = GUIDELINE_DIR / f"{gid}.yaml"
    if not path.exists():
        hint = " (mới có bản nháp trong drafts/, cần người duyệt chuyển ra)" if (
            GUIDELINE_DIR / "drafts" / f"{gid}.yaml").exists() else ""
        raise FileNotFoundError(f"Không có spec {path}{hint}")
    with open(path, encoding="utf-8") as f:
        spec = yaml.safe_load(f) or {}

    missing = [k for k in REQUIRED_KEYS if k not in spec]
    if missing:
        raise ValueError(f"{path.name}: thiếu khoá {missing}")
    if spec["id"] != gid:
        raise ValueError(f"{path.name}: id trong file là {spec['id']!r}, khác {gid!r}")
    if str(spec["version"]) != version:
        raise ValueError(f"{gid}: spec đang ở version {spec['version']}, batch yêu cầu {version}")
    dup = [rid for rid, n in Counter(r["id"] for r in spec["rules"]).items() if n > 1]
    if dup:
        raise ValueError(f"{gid}: rule ID bị trùng {dup}")

    if not str(spec["approved_by"] or "").strip():
        msg = f"Spec {guideline_ref} chưa được duyệt (approved_by rỗng)"
        if not allow_unapproved:
            raise UnapprovedSpecError(msg)
        warnings.warn(msg + ", chỉ dùng khi dev", stacklevel=2)

    spec.setdefault("merge", {})
    spec.setdefault("visual_rules", [])
    spec.setdefault("unclear", [])
    return spec


def spec_for_batch(batch: str, allow_unapproved: bool = False) -> dict | None:
    """Spec của batch theo configs/batches.yaml. None = batch chạy không theo guideline."""
    batches = config.load("batches")
    if batch not in batches:
        raise KeyError(f"Batch {batch!r} chưa có trong configs/batches.yaml")
    ref = batches[batch]
    return load_spec(ref, allow_unapproved) if ref else None


def guideline(objects, images, spec: dict):
    raise NotImplementedError("TODO(Long): chạy CHECKS theo spec, value = 1 - prod(1 - severity)")


SIGNALS = {"guideline": guideline}
