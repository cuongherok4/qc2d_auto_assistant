"""Quy ước dữ liệu để ghép code giữa các thành viên. Không đổi khi chưa báo cả nhóm.

1. Tín hiệu trả về SignalResult (src/features/base.py).
2. data/yolo_preds.parquet: PRED_COLS, category là tên class BDD, toạ độ pixel ảnh gốc 1280x720.
3. reports/ranked_queue_<model_version>.csv: QUEUE_COLS, risk_score 0–100, rank từ 1,
   top_reasons tối đa 3 lý do nối bằng " | ".
"""

from __future__ import annotations

import pandas as pd

BDD_CLASSES = (
    "pedestrian", "rider", "car", "truck", "bus", "train",
    "motorcycle", "bicycle", "traffic light", "traffic sign",
)
IMG_W, IMG_H = 1280, 720
PRED_COLS = ["image_id", "x1", "y1", "x2", "y2", "category", "conf"]
QUEUE_COLS = ["image_id", "risk_score", "rank", "top_reasons", "model_version"]
REASON_SEP = " | "


def check_preds(df: pd.DataFrame) -> list[str]:
    """Trả về danh sách lỗi; rỗng nghĩa là đúng quy ước 2."""
    missing = [c for c in PRED_COLS if c not in df.columns]
    if missing:
        return [f"preds: thiếu cột {missing}"]
    errs = []
    bad_cls = set(df["category"].unique()) - set(BDD_CLASSES)
    if bad_cls:
        errs.append(f"preds: category không phải tên class BDD: {sorted(bad_cls)[:10]}")
    if not df["conf"].between(0, 1).all():
        errs.append("preds: conf nằm ngoài [0, 1]")
    inverted = ((df["x2"] <= df["x1"]) | (df["y2"] <= df["y1"])).sum()
    if inverted:
        errs.append(f"preds: {inverted} box có x2<=x1 hoặc y2<=y1")
    out = ((df["x1"] < -1) | (df["y1"] < -1) | (df["x2"] > IMG_W + 1) | (df["y2"] > IMG_H + 1)).sum()
    if out:
        errs.append(f"preds: {out} box ra ngoài khung {IMG_W}x{IMG_H} (đã scale về ảnh gốc chưa?)")
    if len(df) and df["x2"].max() <= 1.0 + 1e-6:
        errs.append("preds: toạ độ có vẻ đang chuẩn hoá 0–1, cần pixel")
    return errs


def check_queue(df: pd.DataFrame) -> list[str]:
    """Trả về danh sách lỗi; rỗng nghĩa là đúng quy ước 3."""
    missing = [c for c in QUEUE_COLS if c not in df.columns]
    if missing:
        return [f"queue: thiếu cột {missing}"]
    errs = []
    if df["image_id"].duplicated().any():
        errs.append(f"queue: {df['image_id'].duplicated().sum()} image_id bị lặp")
    if not df["risk_score"].between(0, 100).all():
        errs.append("queue: risk_score nằm ngoài [0, 100]")
    if sorted(df["rank"].tolist()) != list(range(1, len(df) + 1)):
        errs.append("queue: rank phải là 1..N liên tục, không trùng")
    if not df.sort_values("rank")["risk_score"].is_monotonic_decreasing:
        errs.append("queue: risk_score phải giảm dần theo rank")
    reasons = df["top_reasons"].fillna("")
    if (reasons.map(lambda s: len([r for r in s.split(REASON_SEP) if r])) > 3).any():
        errs.append("queue: top_reasons có hơn 3 lý do")
    no_digit = reasons.map(lambda s: s != "" and not any(ch.isdigit() for ch in s)).sum()
    if no_digit:
        errs.append(f"queue: {no_digit} dòng có lý do không chứa con số nào")
    if df["model_version"].nunique() > 1:
        errs.append("queue: một file chỉ nên có một model_version")
    return errs
