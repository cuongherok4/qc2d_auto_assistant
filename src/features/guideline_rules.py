"""Bước 3c · Rule engine kiểm nhãn theo spec guideline của batch. Phụ trách: Long.
Hướng dẫn: skill `guideline-rules`.

Đọc configs/guidelines/<id>.yaml (đã duyệt, approved_by khác rỗng). Mỗi `check` trong spec là một hàm
đăng ký trong CHECKS. Kết quả: SignalResult name="guideline", reason bắt đầu bằng rule ID:
"[R1] Box car cao 12px, dưới ngưỡng 15px của guideline".
"""

from __future__ import annotations

import warnings
from collections import Counter

import numpy as np
import pandas as pd
import yaml

from src import config
from src.features.base import SignalResult, Signals

# check -> fn(objects, spec, rule) -> list vi phạm {image_id, obj_id, box, severity, reason}.
# Thêm luật mới = thêm hàm + mục YAML, không sửa engine.
CHECKS: dict = {}  # "below_min_height": fn, "class_not_allowed": fn, "missing_attribute": fn
NEAR_FACTOR = 0.3  # ca sát ngưỡng chỉ tính severity × hệ số này; spec ghi đè bằng near_threshold_factor

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


def check(name: str):
    """Đăng ký hàm kiểm vào CHECKS dưới tên `check` dùng trong spec."""
    def deco(fn):
        CHECKS[name] = fn
        return fn
    return deco


def _num(x) -> int | float:
    return int(x) if float(x).is_integer() else float(x)


def _reason(rule: dict, text: str) -> str:
    page = f" (tr.{rule['page']})" if rule.get("page") else ""
    return f"[{rule['id']}] {text}{page}"


def apply_merge(objects: pd.DataFrame, spec: dict) -> pd.DataFrame:
    """Gộp class theo spec (vd. {bus: truck}) trước mọi kiểm tra."""
    merge = spec.get("merge") or {}
    return objects.assign(category=objects["category"].replace(merge)) if merge else objects


def min_height(categories: pd.Series, spec: dict) -> pd.Series:
    """Ngưỡng chiều cao (px) của từng box: theo class, không có thì lấy default (0 = không kiểm)."""
    thr = spec.get("min_height_px") or {}
    per_class = {k: v for k, v in thr.items() if k != "default"}
    return categories.map(per_class).fillna(thr.get("default", 0)).astype(float)


@check("below_min_height")
def below_min_height(objects: pd.DataFrame, spec: dict, rule: dict) -> list[dict]:
    """R1: box thấp hơn min_height_px của class.

    Thiếu không quá near_threshold_px là "sát ngưỡng": chỉ tính một phần severity và không kết luận
    là lỗi, vì người kéo box lệch vài px là bình thường.
    """
    thr = min_height(objects["category"], spec)
    hits = objects[objects["h"] < thr].assign(thr=thr)
    near_px = spec.get("near_threshold_px", 0)
    factor = spec.get("near_threshold_factor", NEAR_FACTOR)
    out = []
    for r in hits.itertuples(index=False):
        ctx = {"category": r.category, "obj_id": r.obj_id, "h": r.h, "thr": _num(r.thr), "gid": spec["id"]}
        if r.thr - r.h <= near_px:
            severity = rule["severity"] * factor
            text = (f"Box {r.category} #{r.obj_id} cao {r.h:.0f}px, "
                    f"sát ngưỡng {ctx['thr']}px, chưa chắc là lỗi")
        else:
            severity = rule["severity"]
            text = rule["message"].format(**ctx)
        out.append({"image_id": r.image_id, "obj_id": r.obj_id, "box": [r.x1, r.y1, r.x2, r.y2],
                    "severity": severity, "reason": _reason(rule, text)})
    return out


def guideline(objects: pd.DataFrame, images: pd.DataFrame, spec: dict) -> Signals:
    """Chạy mọi rule của spec trên mọi ảnh.

    value của ảnh = 1 - prod(1 - severity_i); reason là vi phạm nặng nhất, evidence gồm mọi vi phạm.
    Rule có `check` chưa đăng ký thì cảnh báo và bỏ qua.
    """
    objects = apply_merge(objects, spec)
    violations = []
    for rule in spec["rules"]:
        fn = CHECKS.get(rule["check"])
        if fn is None:
            warnings.warn(f"{spec['id']}: chưa có hàm cho check {rule['check']!r} ({rule['id']}), bỏ qua",
                          stacklevel=2)
            continue
        violations += fn(objects, spec, rule)

    by_image: dict[str, list[dict]] = {}
    for v in violations:
        by_image.setdefault(v["image_id"], []).append(v)

    out = {}
    for img in images["image_id"]:
        vs = sorted(by_image.get(img, []), key=lambda v: -v["severity"])
        if not vs:
            out[img] = SignalResult("guideline", 0.0)
            continue
        value = float(1 - np.prod([1 - v["severity"] for v in vs]))
        more = f" (+{len(vs) - 1} vi phạm khác)" if len(vs) > 1 else ""
        evidence = [{"obj_id": v["obj_id"], "box": v["box"], "note": v["reason"]} for v in vs]
        out[img] = SignalResult("guideline", value, vs[0]["reason"] + more, evidence)
    return out


SIGNALS = {"guideline": guideline}
