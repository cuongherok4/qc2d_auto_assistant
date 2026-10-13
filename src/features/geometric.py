"""Bước 3a · Tín hiệu hình học / ngữ cảnh (phần khó). Phụ trách: Cường. Hướng dẫn: skill `qc-signals` mục a.
4 tín hiệu dễ (crowded, many_tiny, rare_class, edge_no_trunc) nằm ở simple_signals.py (Long).

Mỗi hàm: (objects, images, cfg) -> Signals, trả kết quả cho MỌI ảnh trong `images`.
Ngưỡng mặc định ở DEFAULTS; ghi đè qua configs/pipeline.yaml signal_options.
Thống kê (median, MAD, tần suất class) tính trên chính file nhãn đang chấm, không dùng nhãn sạch.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.features.base import SignalResult, Signals
from src.features.geometry import iou_matrix

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


DEFAULTS = {
    # |z| robust (median/MAD theo class) của log diện tích hoặc log tỉ lệ rộng/cao; z_thr -> 0, z_sat -> 1
    "size_outlier": {"z_thr": 3.0, "z_sat": 6.0, "min_class_count": 30},
    # cặp box cùng class IoU > iou_thr: nghi gán trùng. Cặp ở ngưỡng -> 0.5, trùng khít -> 1
    "dup_same_class": {"iou_thr": 0.5},
    # cặp box khác class IoU > iou_thr: nghi sai class; trừ các cặp hợp lệ (người ngồi trên xe)
    "overlap_cross_class": {"iou_thr": 0.7,
                            "allowed_pairs": [["rider", "bicycle"], ["rider", "motorcycle"]]},
}


def _params(name: str, cfg: dict | None) -> dict:
    return {**DEFAULTS[name], **((cfg or {}).get(name) or {})}


def _empty(name: str, images: pd.DataFrame) -> Signals:
    return {img: SignalResult(name, 0.0) for img in images["image_id"]}


def _box(r) -> list[float]:
    return [float(r.x1), float(r.y1), float(r.x2), float(r.y2)]


def size_outlier(objects, images, cfg=None) -> Signals:
    """Box có diện tích hoặc tỉ lệ rộng/cao lệch xa các box cùng class (z robust trên log).
    Bắt box bị co/giãn, box giả và box gán nhầm class (car to bằng bus...)."""
    p = _params("size_outlier", cfg)
    out = _empty("size_outlier", images)
    obj = objects[(objects["w"] > 0) & (objects["h"] > 0)].copy()
    if obj.empty:
        return out
    obj["log_area"] = np.log(obj["area"])
    obj["log_ratio"] = np.log(obj["w"] / obj["h"])
    by = obj.groupby("category")
    obj = obj[by["category"].transform("size") >= p["min_class_count"]].copy()
    if obj.empty:
        return out
    by = obj.groupby("category")
    for col in ("log_area", "log_ratio"):
        med = by[col].transform("median")
        mad = (obj[col] - med).abs().groupby(obj["category"]).transform("median") * 1.4826
        obj[f"z_{col}"] = np.where(mad > 0, (obj[col] - med) / mad.where(mad > 0, 1), 0.0)
    obj["pct_area"] = by["area"].rank(pct=True) * 100
    obj["z"] = obj[["z_log_area", "z_log_ratio"]].abs().max(axis=1)
    hits = obj[obj["z"] > p["z_thr"]]
    for img, g in hits.groupby("image_id", sort=False):
        if img not in out:
            continue
        ev = []
        for r in g.sort_values("z", ascending=False).itertuples(index=False):
            if abs(r.z_log_area) >= abs(r.z_log_ratio):
                side = "nhỏ hơn" if r.z_log_area < 0 else "lớn hơn"
                share = r.pct_area if r.z_log_area > 0 else 100 - r.pct_area
                note = (f"{r.category} #{r.obj_id} {r.w:.0f}x{r.h:.0f}px, {side} {share:.0f}% "
                        f"{r.category} khác (z={r.z_log_area:+.1f})")
            else:
                note = (f"{r.category} #{r.obj_id} tỉ lệ rộng/cao {r.w / r.h:.2f}, "
                        f"bất thường so với {r.category} khác (z={r.z_log_ratio:+.1f})")
            ev.append({"obj_id": r.obj_id, "box": _box(r), "note": note})
        zmax = float(g["z"].max())
        value = min(1.0, 0.1 + 0.9 * (zmax - p["z_thr"]) / (p["z_sat"] - p["z_thr"]))
        reason = f"Box {ev[0]['note']}" + (f"; thêm {len(ev) - 1} box lệch cỡ" if len(ev) > 1 else "")
        out[img] = SignalResult("size_outlier", value, reason, ev)
    return out


def _overlaps(objects: pd.DataFrame, iou_thr: float, same_class: bool, allowed=()) -> list[tuple]:
    """Mọi cặp box trong cùng ảnh có IoU > iou_thr, lọc theo cùng/khác class."""
    allowed = {frozenset(pair) for pair in allowed}
    rows = []
    for img, g in objects.groupby("image_id", sort=False):
        if len(g) < 2:
            continue
        iou = iou_matrix(g[["x1", "y1", "x2", "y2"]].to_numpy(), g[["x1", "y1", "x2", "y2"]].to_numpy())
        cats = g["category"].to_numpy()
        same = cats[:, None] == cats[None, :]
        mask = np.triu(iou > iou_thr, k=1) & (same if same_class else ~same)
        for i, j in zip(*np.nonzero(mask), strict=True):
            if frozenset((cats[i], cats[j])) in allowed:
                continue
            rows.append((img, g.iloc[i], g.iloc[j], float(iou[i, j])))
    return rows


def _pair_signal(name, objects, images, iou_thr, same_class, allowed=()) -> Signals:
    out = _empty(name, images)
    by_image: dict[str, list] = {}
    for img, a, b, iou in _overlaps(objects, iou_thr, same_class, allowed):
        by_image.setdefault(img, []).append((a, b, iou))
    for img, pairs in by_image.items():
        if img not in out:
            continue
        pairs.sort(key=lambda t: -t[2])
        a, b, iou = pairs[0]
        if same_class:
            reason = f"2 box {a.category} #{a.obj_id} và #{b.obj_id} trùng nhau IoU {iou:.2f}"
        else:
            reason = (f"Box {a.category} #{a.obj_id} và {b.category} #{b.obj_id} chồng khít "
                      f"IoU {iou:.2f}, nghi sai class")
        if len(pairs) > 1:
            reason += f"; tổng {len(pairs)} cặp"
        ev = []
        for a, b, iou in pairs:
            for r, other in ((a, b), (b, a)):
                ev.append({"obj_id": r.obj_id, "box": _box(r),
                           "note": f"chồng {other.category} #{other.obj_id}, IoU {iou:.2f}"})
        value = min(1.0, 0.5 + 0.5 * (iou - iou_thr) / (1 - iou_thr))
        out[img] = SignalResult(name, value, reason, ev)
    return out


def dup_same_class(objects, images, cfg=None) -> Signals:
    """Hai box cùng class chồng nhau IoU > iou_thr: nghi gán trùng một vật."""
    p = _params("dup_same_class", cfg)
    return _pair_signal("dup_same_class", objects, images, p["iou_thr"], same_class=True)


def overlap_cross_class(objects, images, cfg=None) -> Signals:
    """Hai box khác class chồng khít IoU > iou_thr: nghi một vật bị gán hai class."""
    p = _params("overlap_cross_class", cfg)
    return _pair_signal("overlap_cross_class", objects, images, p["iou_thr"], same_class=False,
                        allowed=p["allowed_pairs"])


SIGNALS = {
    "hard_condition": hard_condition,
    "size_outlier": size_outlier,
    "dup_same_class": dup_same_class,
    "overlap_cross_class": overlap_cross_class,
}
