"""Bước 3b (phần 2) · Bất đồng giữa nhãn và detector. Phụ trách: Sơn. Hướng dẫn: skill `qc-signals` mục b.

Đầu vào: bảng objects + data/yolo_preds.parquet (src/features/detector.py sinh ra).
Mỗi hàm: (objects, images, preds, cfg) -> Signals, trả kết quả cho MỌI ảnh trong `images`.

Khớp một lần cho cả 4 tín hiệu (_match): từng ảnh, Hungarian trên 1 - IoU (+ phạt khác class) giữa nhãn và
dự đoán conf >= match_conf, IoU >= min_iou mới coi là cùng object (riêng box lệch: IoU >= loose_min_iou).
Dự đoán dạng capo xe mình bị bỏ trước khi khớp. COCO không có rider và traffic sign: hai class này
vẫn tham gia khớp (để dự đoán đè lên chúng không bị báo "thiếu box") nhưng không bao giờ bị báo
sai class / box giả; dự đoán pedestrian khớp nhãn rider coi là đồng ý.
Nếu có spec guideline: gộp class theo `merge`, bỏ dự đoán thấp hơn min_height_px,
ngưỡng box lệch lấy `iou_loose`.
Ngưỡng mặc định ở DEFAULTS; ghi đè qua configs/pipeline.yaml detector_options.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment

from src.features.base import SignalResult, Signals
from src.features.geometry import iou_matrix

DEFAULTS = {
    "match_conf": 0.3,      # dự đoán dưới ngưỡng này không tham gia khớp
    "nms_iou": 0.7,         # RT-DETR không NMS: gộp dự đoán trùng nhau trước khi khớp
    "min_iou": 0.5,         # IoU tối thiểu để coi là cùng object
    "loose_min_iou": 0.3,   # riêng box lệch: box dịch ~1/3 bề rộng đã có IoU < min_iou
    "class_penalty": 0.3,   # cộng vào chi phí khi khác class, để ưu tiên khớp cùng class
    "loose_iou": 0.7,       # cùng class nhưng IoU dưới ngưỡng này -> box lệch (spec iou_loose ghi đè)
    "missing_conf": 0.5,    # dự đoán không khớp, conf >= ngưỡng -> nghi thiếu box
    "missing_max_iou": 0.3,  # ...và không chồng nhãn nào quá ngưỡng này
    "conflict_conf": 0.5,   # khớp nhưng khác class, model conf >= ngưỡng -> nghi sai class
    "loose_conf": 0.5,
    "min_h": 15.0,          # bỏ object thấp hơn (px) khỏi missing/conflict/loose: detector kém ở vật nhỏ
    "unsupported_min_h": 40.0,  # nhãn cao từ ngưỡng này mà không dự đoán nào gần -> nghi box giả
    "support_conf": 0.1,    # dự đoán conf >= ngưỡng này có IoU >= support_iou là đủ "có hỗ trợ"
    "support_iou": 0.3,
    "h_sat": 60.0,          # vật cao từ ngưỡng này có trọng số kích thước đầy đủ
    "ego_min_y2": 715.0,    # dự đoán chạm đáy ảnh và rộng từ ego_min_w là capo xe mình (BDD không gán): bỏ
    "ego_min_w": 640.0,
    "no_model_classes": ["rider", "traffic sign"],
    "compatible": [["rider", "pedestrian"]],  # [nhãn, dự đoán] coi là cùng class
}

_CACHE: dict = {}


def _params(cfg: dict | None) -> dict:
    cfg = dict(cfg or {})
    spec = cfg.pop("spec", None)
    p = {**DEFAULTS, **cfg}
    if spec and spec.get("iou_loose"):
        p["loose_iou"] = float(spec["iou_loose"])
    return p, spec


def _nms(boxes: np.ndarray, conf: np.ndarray, thr: float) -> np.ndarray:
    """Giữ chỉ số các dự đoán sau NMS không phân biệt class (đã sắp conf giảm dần)."""
    keep, order = [], np.argsort(-conf, kind="stable")
    iou = iou_matrix(boxes, boxes)
    dropped = np.zeros(len(boxes), dtype=bool)
    for i in order:
        if dropped[i]:
            continue
        keep.append(i)
        dropped |= iou[i] > thr
    return np.array(keep, dtype=int)


def _filter_preds(preds: pd.DataFrame, p: dict, spec: dict | None) -> pd.DataFrame:
    preds = preds[preds["conf"] >= min(p["match_conf"], p["support_conf"])].copy()
    ego = (preds["y2"] >= p["ego_min_y2"]) & ((preds["x2"] - preds["x1"]) >= p["ego_min_w"])
    preds = preds[~ego]
    if spec:
        from src.features.guideline_rules import min_height

        merge = spec.get("merge") or {}
        if merge:
            preds["category"] = preds["category"].replace(merge)
        preds = preds[(preds["y2"] - preds["y1"]) >= min_height(preds["category"], spec)]
    return preds


def _match(objects: pd.DataFrame, images: pd.DataFrame, preds: pd.DataFrame, cfg: dict | None) -> dict:
    """{image_id: dict(labels, preds, pairs, support)}; tính một lần, 4 tín hiệu dùng chung."""
    p, spec = _params(cfg)
    key = (repr(sorted(p.items())), repr(spec))
    src = (objects, images, preds)  # giữ tham chiếu để so bằng `is`, không dùng id() có thể bị tái sử dụng
    if _CACHE.get("key") == key and all(a is b for a, b in zip(_CACHE["src"], src, strict=True)):
        return _CACHE["value"]
    if spec and spec.get("merge"):
        objects = objects.assign(category=objects["category"].replace(spec["merge"]))
    preds = _filter_preds(preds, p, spec)
    compat = {tuple(x) for x in p["compatible"]}
    label_groups = {k: g for k, g in objects.groupby("image_id", sort=False)}
    pred_groups = {k: g for k, g in preds.groupby("image_id", sort=False)}
    cols = ["x1", "y1", "x2", "y2"]
    out = {}
    for img in images["image_id"]:
        lab = label_groups.get(img, objects.iloc[:0])
        pr = pred_groups.get(img, preds.iloc[:0])
        lb = lab[cols].to_numpy(float)
        support = iou_matrix(lb, pr[cols].to_numpy(float))  # mọi dự đoán >= support_conf
        support = support * (pr["conf"].to_numpy() >= p["support_conf"])[None, :]
        pr = alt = pr[pr["conf"] >= p["match_conf"]]
        pb, pc = pr[cols].to_numpy(float), pr["conf"].to_numpy(float)
        alt_iou = iou_matrix(lb, pb)  # trước NMS: để biết model có phân vân giữa hai class không
        if len(pr):
            keep = _nms(pb, pc, p["nms_iou"])
            pr, pb, pc = pr.iloc[keep], pb[keep], pc[keep]
        iou = iou_matrix(lb, pb)
        pairs = []
        if iou.size:
            lc, pcat = lab["category"].to_numpy(), pr["category"].to_numpy()
            same = (lc[:, None] == pcat[None, :]) | np.array(
                [[(a, b) in compat for b in pcat] for a in lc], dtype=bool).reshape(iou.shape)
            rows, colsi = linear_sum_assignment(1.0 - iou + p["class_penalty"] * ~same)
            pairs = [(int(i), int(j), float(iou[i, j]), bool(same[i, j]))
                     for i, j in zip(rows, colsi, strict=True)
                     if iou[i, j] >= min(p["min_iou"], p["loose_min_iou"])]
        out[img] = {"labels": lab, "preds": pr, "iou": iou, "pairs": pairs, "support": support,
                    "alt": alt, "alt_iou": alt_iou}
    _CACHE.update(key=key, src=src, value=out)
    return out


def _box(r) -> list[float]:
    return [round(float(r.x1), 1), round(float(r.y1), 1), round(float(r.x2), 1), round(float(r.y2), 1)]


def _size_w(h: float, p: dict) -> float:
    return min(1.0, h / p["h_sat"])


def _signal(name: str, images: pd.DataFrame, items: dict) -> Signals:
    """items: {image_id: [(score, reason, evidence)]}.
    value = điểm mục mạnh nhất + 0.1 mỗi mục thêm; reason là lý do của mục mạnh nhất."""
    out = {}
    for img in images["image_id"]:
        hits = sorted(items.get(img, []), key=lambda x: -x[0])
        if not hits:
            out[img] = SignalResult(name, 0.0)
            continue
        value = min(1.0, hits[0][0] + 0.1 * (len(hits) - 1))
        reason = hits[0][1] + (f" (+{len(hits) - 1} chỗ khác)" if len(hits) > 1 else "")
        out[img] = SignalResult(name, round(value, 4), reason, [x for _, _, ev in hits for x in ev])
    return out


def model_missing_label(objects, images, preds, cfg=None) -> Signals:
    """Dự đoán conf cao không khớp và không chồng nhãn nào -> nghi thiếu box."""
    p, _ = _params(cfg)
    items = {}
    for img, m in _match(objects, images, preds, cfg).items():
        matched = {j for _, j, _, _ in m["pairs"]}
        max_iou = m["iou"].max(axis=0) if m["iou"].size else np.zeros(len(m["preds"]))
        for j, r in enumerate(m["preds"].itertuples(index=False)):
            h = r.y2 - r.y1
            if j in matched or r.conf < p["missing_conf"] or h < p["min_h"] \
                    or max_iou[j] >= p["missing_max_iou"]:
                continue
            score = r.conf * _size_w(h, p)
            items.setdefault(img, []).append((score, (
                f"Model thấy {r.category} cao {h:.0f}px (conf {r.conf:.2f}), nhãn không có box nào trùng"),
                [{"obj_id": None, "box": _box(r), "note": f"model: {r.category} {r.conf:.2f}"}]))
    return _signal("model_missing_label", images, items)


def model_class_conflict(objects, images, preds, cfg=None) -> Signals:
    """Khớp nhưng khác class, model conf cao, và không dự đoán nào cùng class với nhãn ở đó
    -> nghi sai class."""
    p, _ = _params(cfg)
    skip = set(p["no_model_classes"])
    compat = {tuple(x) for x in p["compatible"]}
    items = {}
    for img, m in _match(objects, images, preds, cfg).items():
        lab, pr = m["labels"], m["preds"]
        for i, j, iou, same in m["pairs"]:
            lr, r = lab.iloc[i], pr.iloc[j]
            if same or iou < p["min_iou"] or lr.category in skip or r.conf < p["conflict_conf"] \
                    or lr.h < p["min_h"]:
                continue
            agree = [(lr.category == c or (lr.category, c) in compat) and m["alt_iou"][i, k] >= p["min_iou"]
                     for k, c in enumerate(m["alt"]["category"])]
            if any(agree):  # model cũng thấy class của nhãn ở đó (kể cả bị NMS bỏ): còn phân vân, không báo
                continue
            score = r.conf * _size_w(lr.h, p)
            items.setdefault(img, []).append((score, (
                f"Nhãn {lr.category} #{lr.obj_id} nhưng model thấy {r.category} "
                f"(conf {r.conf:.2f}, IoU {iou:.2f})"),
                [{"obj_id": lr.obj_id, "box": _box(lr), "note": f"nhãn: {lr.category}"},
                 {"obj_id": None, "box": _box(r), "note": f"model: {r.category} {r.conf:.2f}"}]))
    return _signal("model_class_conflict", images, items)


def model_loose_box(objects, images, preds, cfg=None) -> Signals:
    """Khớp cùng class nhưng loose_min_iou <= IoU < loose_iou -> nghi box lệch/co giãn."""
    p, _ = _params(cfg)
    span = max(p["loose_iou"] - p["loose_min_iou"], 1e-6)
    items = {}
    for img, m in _match(objects, images, preds, cfg).items():
        lab, pr = m["labels"], m["preds"]
        for i, j, iou, same in m["pairs"]:
            lr, r = lab.iloc[i], pr.iloc[j]
            if not same or not p["loose_min_iou"] <= iou < p["loose_iou"] or r.conf < p["loose_conf"] \
                    or lr.h < p["min_h"]:
                continue
            score = (0.5 + 0.5 * (p["loose_iou"] - iou) / span) * r.conf * _size_w(lr.h, p)
            items.setdefault(img, []).append((score, (
                f"Box {lr.category} #{lr.obj_id} lệch so với model: IoU {iou:.2f} < {p['loose_iou']:.2f} "
                f"(conf {r.conf:.2f})"),
                [{"obj_id": lr.obj_id, "box": _box(lr), "note": "nhãn"},
                 {"obj_id": None, "box": _box(r), "note": f"model: {r.category} {r.conf:.2f}"}]))
    return _signal("model_loose_box", images, items)


def label_unsupported(objects, images, preds, cfg=None) -> Signals:
    """Nhãn lớn mà không dự đoán nào (kể cả conf thấp) chồng lên -> nghi box giả.
    Yếu: model hay sót vật bị che."""
    p, _ = _params(cfg)
    skip = set(p["no_model_classes"])
    items = {}
    for img, m in _match(objects, images, preds, cfg).items():
        lab = m["labels"]
        best = m["support"].max(axis=1) if m["support"].size else np.zeros(len(lab))
        for i, lr in enumerate(lab.itertuples(index=False)):
            if lr.category in skip or lr.h < p["unsupported_min_h"] or best[i] >= p["support_iou"]:
                continue
            score = min(1.0, lr.h / (2 * p["unsupported_min_h"])) * (0.5 if lr.occluded else 1.0)
            items.setdefault(img, []).append((score, (
                f"Box {lr.category} #{lr.obj_id} cao {lr.h:.0f}px nhưng model không thấy gì ở đó "
                f"(IoU lớn nhất {best[i]:.2f})"),
                [{"obj_id": lr.obj_id, "box": _box(lr), "note": "không có dự đoán"}]))
    return _signal("label_unsupported", images, items)


SIGNALS = {
    "model_missing_label": model_missing_label,
    "model_class_conflict": model_class_conflict,
    "model_loose_box": model_loose_box,
    "label_unsupported": label_unsupported,
}
