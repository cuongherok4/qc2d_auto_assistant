"""Bước 3a · 4 tín hiệu hình học / ngữ cảnh dễ. Phụ trách: Long. Hướng dẫn: skill `qc-signals` mục a.

Làm theo khuôn của `hard_condition` trong geometric.py: (objects, images, cfg) -> Signals,
trả kết quả cho MỌI ảnh trong `images` (ảnh không kích hoạt: value=0, reason="").
Thống kê tính trên chính file nhãn đang chấm (đã tiêm lỗi), không dùng nhãn sạch.

Ngưỡng mặc định ở DEFAULTS; truyền `cfg` để ghi đè (sẽ chuyển vào configs/ khi nhóm chốt chỗ để).
"""

from __future__ import annotations

import pandas as pd

from src.features.base import SignalResult, Signals
from src.features.geometry import IMG_H, IMG_W, touches_edge

DEFAULTS = {
    "crowded": {"pct_low": 75, "pct_high": 99},  # bách phân vị số box: 75 -> value 0, 99 -> value 1
    "many_tiny": {"max_h": 20, "min_count": 3, "saturate": 10},  # >= 3 box thấp < 20px; 10 box -> 1
    "rare_class": {"max_share": 0.01},  # class chiếm < 1% số box toàn tập
    "edge_no_trunc": {"margin": 2.0, "saturate": 2},  # 2 box chạm mép không truncated -> 1
}


def _params(name: str, cfg: dict | None) -> dict:
    """cfg dạng {"many_tiny": {"max_h": 15}}: chỉ ghi đè tham số được truyền."""
    return {**DEFAULTS[name], **((cfg or {}).get(name) or {})}


def _empty(name: str, images: pd.DataFrame) -> Signals:
    return {img: SignalResult(name, 0.0) for img in images["image_id"]}


def _evidence(rows: pd.DataFrame, note: str) -> list[dict]:
    return [{"obj_id": r.obj_id, "box": [r.x1, r.y1, r.x2, r.y2], "note": note.format(r=r)}
            for r in rows.itertuples(index=False)]


def crowded(objects: pd.DataFrame, images: pd.DataFrame, cfg: dict | None = None) -> Signals:
    """Ảnh nhiều box hơn phần lớn tập: dễ sót. value tăng tuyến tính từ bách phân vị pct_low tới pct_high."""
    p = _params("crowded", cfg)
    out = _empty("crowded", images)
    if images.empty:
        return out
    n = images["n_boxes"]
    # ảnh hoà số box lấy hạng thấp nhất: số box phổ biến không bị đẩy lên bách phân vị cao
    pct = n.rank(pct=True, method="min") * 100
    value = ((pct - p["pct_low"]) / (p["pct_high"] - p["pct_low"])).clip(0, 1)
    for img, k, q, v in zip(images["image_id"], n, pct, value, strict=True):
        if v > 0 and k > 0:
            out[img] = SignalResult("crowded", float(v), f"Ảnh đông {k} box (bách phân vị {q:.0f})")
    return out


def many_tiny(objects: pd.DataFrame, images: pd.DataFrame, cfg: dict | None = None) -> Signals:
    """Nhiều box cao < max_h px: vật nhỏ/xa dễ bị sót hoặc kéo lệch."""
    p = _params("many_tiny", cfg)
    out = _empty("many_tiny", images)
    tiny = objects[objects["h"] < p["max_h"]]
    for img, g in tiny.groupby("image_id", sort=False):
        if img not in out or len(g) < p["min_count"]:
            continue
        smallest = g.loc[g["h"].idxmin()]
        reason = (f"{len(g)} box cao dưới {p['max_h']}px "
                  f"(nhỏ nhất {smallest.category} #{smallest.obj_id} cao {smallest.h:.0f}px)")
        out[img] = SignalResult("many_tiny", min(1.0, len(g) / p["saturate"]), reason,
                                _evidence(g, "cao {r.h:.0f}px"))
    return out


def rare_class(objects: pd.DataFrame, images: pd.DataFrame, cfg: dict | None = None) -> Signals:
    """Ảnh có class hiếm (< max_share số box toàn tập). Chỉ là ngữ cảnh: class hiếm dễ bị gán nhầm.
    value = 1 - share / max_share của class hiếm nhất trong ảnh."""
    p = _params("rare_class", cfg)
    out = _empty("rare_class", images)
    if objects.empty:
        return out
    share = objects["category"].value_counts(normalize=True)
    rare = share[share < p["max_share"]]
    hits = objects[objects["category"].isin(rare.index)].assign(share=lambda d: d["category"].map(rare))
    for img, g in hits.groupby("image_id", sort=False):
        if img not in out:
            continue
        top = g.loc[g["share"].idxmin()]
        n_same = int((g["category"] == top.category).sum())
        reason = f"Có {n_same} box {top.category}, class chỉ chiếm {100 * top.share:.2f}% số box toàn tập"
        out[img] = SignalResult("rare_class", float(1 - top.share / p["max_share"]), reason,
                                _evidence(g, "class hiếm {r.category}"))
    return out


def _edge_name(r, margin: float) -> str:
    hits = (("trái", r.x1 <= margin), ("trên", r.y1 <= margin),
            ("phải", r.x2 >= IMG_W - margin), ("dưới", r.y2 >= IMG_H - margin))
    sides = [name for name, hit in hits if hit]
    return ", ".join(sides)


def edge_no_trunc(objects: pd.DataFrame, images: pd.DataFrame, cfg: dict | None = None) -> Signals:
    """Box cách mép ảnh < margin px mà truncated=false: thiếu thuộc tính truncated."""
    p = _params("edge_no_trunc", cfg)
    out = _empty("edge_no_trunc", images)
    if objects.empty:
        return out
    box = objects[["x1", "y1", "x2", "y2"]].to_numpy()
    hits = objects[touches_edge(box, p["margin"]) & ~objects["truncated"].astype(bool)]
    for img, g in hits.groupby("image_id", sort=False):
        if img not in out:
            continue
        first = g.iloc[0]
        reason = (f"{len(g)} box chạm mép nhưng không gắn truncated, "
                  f"vd. {first.category} #{first.obj_id} (mép {_edge_name(first, p['margin'])})")
        ev = [{**e, "note": f"chạm mép {_edge_name(r, p['margin'])}, truncated=false"}
              for e, r in zip(_evidence(g, ""), g.itertuples(index=False), strict=True)]
        out[img] = SignalResult("edge_no_trunc", min(1.0, len(g) / p["saturate"]), reason, ev)
    return out


SIGNALS = {
    "crowded": crowded,
    "many_tiny": many_tiny,
    "rare_class": rare_class,
    "edge_no_trunc": edge_no_trunc,
}
