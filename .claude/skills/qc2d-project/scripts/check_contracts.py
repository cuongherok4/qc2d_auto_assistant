"""Kiểm file dữ liệu có đúng 3 quy ước ghép code của M13 hay không.

Dùng:
    python check_contracts.py --preds data/yolo_preds.parquet
    python check_contracts.py --queue reports/ranked_queue_rule.csv
    python check_contracts.py --make-samples data/samples   # tạo file mẫu đúng schema

Thoát mã 1 nếu có lỗi, in từng lỗi một dòng.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

BDD_CLASSES = {
    "pedestrian", "rider", "car", "truck", "bus", "train",
    "motorcycle", "bicycle", "traffic light", "traffic sign",
}
IMG_W, IMG_H = 1280, 720
PRED_COLS = ["image_id", "x1", "y1", "x2", "y2", "category", "conf"]
QUEUE_COLS = ["image_id", "risk_score", "rank", "top_reasons", "model_version"]


def check_preds(df: pd.DataFrame) -> list[str]:
    errs = []
    missing = [c for c in PRED_COLS if c not in df.columns]
    if missing:
        return [f"preds: thiếu cột {missing}"]
    bad_cls = set(df["category"].unique()) - BDD_CLASSES
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
    if df["x2"].max() <= 1.0 + 1e-6 and len(df):
        errs.append("preds: toạ độ có vẻ đang chuẩn hoá 0–1, cần pixel")
    return errs


def check_queue(df: pd.DataFrame) -> list[str]:
    errs = []
    missing = [c for c in QUEUE_COLS if c not in df.columns]
    if missing:
        return [f"queue: thiếu cột {missing}"]
    if df["image_id"].duplicated().any():
        errs.append(f"queue: {df['image_id'].duplicated().sum()} image_id bị lặp")
    if not df["risk_score"].between(0, 100).all():
        errs.append("queue: risk_score nằm ngoài [0, 100]")
    ranks = df["rank"].sort_values().tolist()
    if ranks != list(range(1, len(df) + 1)):
        errs.append("queue: rank phải là 1..N liên tục, không trùng")
    ordered = df.sort_values("rank")
    if not ordered["risk_score"].is_monotonic_decreasing:
        errs.append("queue: risk_score phải giảm dần theo rank")
    n_reasons = df["top_reasons"].fillna("").map(lambda s: len([r for r in s.split(" | ") if r]))
    if (n_reasons > 3).any():
        errs.append("queue: top_reasons có hơn 3 lý do")
    no_digit = df["top_reasons"].fillna("").map(lambda s: s != "" and not any(ch.isdigit() for ch in s)).sum()
    if no_digit:
        errs.append(f"queue: {no_digit} dòng có lý do không chứa con số nào")
    if df["model_version"].nunique() > 1:
        errs.append("queue: một file chỉ nên có một model_version")
    return errs


def make_samples(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    preds = pd.DataFrame([
        ["b1c66a42-6f7d68ca", 100.0, 300.0, 260.0, 420.0, "car", 0.91],
        ["b1c66a42-6f7d68ca", 640.0, 200.0, 660.0, 250.0, "traffic light", 0.55],
        ["b1c81faa-3df17267", 50.0, 310.0, 90.0, 420.0, "pedestrian", 0.78],
    ], columns=PRED_COLS)
    preds.to_parquet(out_dir / "yolo_preds.parquet", index=False)
    queue = pd.DataFrame([
        ["b1c66a42-6f7d68ca", 87.5, 1, "Thiếu car cao 120px, model chắc 0.91 | Ảnh đêm, 23 box", "rule-v0"],
        ["b1c81faa-3df17267", 12.0, 2, "Ảnh đông 31 box (bách phân vị 92)", "rule-v0"],
    ], columns=QUEUE_COLS)
    queue.to_csv(out_dir / "ranked_queue_sample.csv", index=False)
    print(f"Đã tạo file mẫu trong {out_dir}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--preds", type=Path)
    ap.add_argument("--queue", type=Path)
    ap.add_argument("--make-samples", type=Path)
    args = ap.parse_args()

    if args.make_samples:
        make_samples(args.make_samples)
        return 0
    errs: list[str] = []
    if args.preds:
        errs += check_preds(pd.read_parquet(args.preds))
    if args.queue:
        errs += check_queue(pd.read_csv(args.queue))
    if not (args.preds or args.queue):
        ap.error("cần --preds, --queue hoặc --make-samples")
    for e in errs:
        print(e)
    print("OK" if not errs else f"{len(errs)} lỗi")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
