"""Bước 7 · Đánh giá một hàng đợi trên đáp án tiêm lỗi, ghi một dòng vào reports/results.jsonl.
Phụ trách: Cường. Hướng dẫn: skill `qc-eval`. Công thức ở src/eval/metrics.py, không viết lại.
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path

import pandas as pd

from src.eval import metrics


def evaluate(queue: pd.DataFrame, answer: dict, split: str = "test", top_frac: float = 0.2) -> dict:
    """queue: ranked_queue (quy ước 3); answer: nội dung injected_errors.json."""
    ids = {i for i, s in answer["splits"].items() if s == split}
    ranked = [i for i in queue.sort_values("rank")["image_id"] if i in ids]
    errors = [e for e in answer["errors"] if e["image_id"] in ids]
    weights = answer["meta"].get("weights", metrics.DEFAULT_WEIGHTS)
    mass_w = metrics.error_mass(errors, weights)
    mass_img = metrics.error_mass(errors, weights, weighted=False)
    return {
        "method": queue["model_version"].iloc[0].split("-")[0],
        "model_version": queue["model_version"].iloc[0],
        "split": split,
        "seed": answer["meta"].get("seed"),
        "n_images": len(ranked),
        "recall20_img": metrics.recall_at(ranked, mass_img, top_frac),
        "recall20_weighted": metrics.recall_at(ranked, mass_w, top_frac),
        "precision20": metrics.precision_at(ranked, mass_img, top_frac),
        "ndcg": metrics.ndcg(ranked, mass_w),
        "time_saved": metrics.time_saved(ranked, mass_w),
        "per_type": metrics.recall_by_type(ranked, errors, top_frac),
    }


def append_result(result: dict, path: Path) -> None:
    """Chỉ thêm dòng, không sửa dòng cũ. Kèm thời gian và commit để chạy lại được."""
    try:
        commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True,
                                text=True, check=True).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        commit = "nogit"
    row = {"ts": datetime.now().isoformat(timespec="seconds"), "commit": commit, **result}
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
