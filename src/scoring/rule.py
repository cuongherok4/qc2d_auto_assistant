"""Bước 4 · Chấm điểm rule: risk = 100 * sum(w * value) / sum(w), top 3 lý do theo w * value.
Phụ trách: Cường. Hướng dẫn: skill `risk-scoring`.

Đầu ra đúng quy ước 3 (src/contracts.py: QUEUE_COLS). Hoà điểm xếp theo image_id để kết quả xác định.
"""

from __future__ import annotations

import pandas as pd

from src.contracts import QUEUE_COLS, REASON_SEP
from src.features.base import Signals


def rank(signals: dict[str, Signals], weights: dict[str, float], model_version: str,
         top_k: int = 3) -> pd.DataFrame:
    """signals: {tên tín hiệu: {image_id: SignalResult}}. Tín hiệu không có trọng số bị bỏ qua."""
    used = {n: s for n, s in signals.items() if weights.get(n, 0) > 0}
    if not used:
        raise ValueError("Không có tín hiệu nào có trọng số trong configs/weights.yaml")
    total_w = sum(weights[n] for n in used)
    image_ids = sorted(set().union(*(s.keys() for s in used.values())))
    rows = []
    for img in image_ids:
        contrib = [(weights[n] * s[img].value, s[img].reason) for n, s in used.items() if img in s]
        score = 100 * sum(c for c, _ in contrib) / total_w
        reasons = [r for c, r in sorted(contrib, key=lambda x: -x[0]) if c > 0 and r][:top_k]
        rows.append({"image_id": img, "risk_score": round(score, 2), "top_reasons": REASON_SEP.join(reasons)})
    df = pd.DataFrame(rows).sort_values(["risk_score", "image_id"], ascending=[False, True])
    df["rank"] = range(1, len(df) + 1)
    df["model_version"] = model_version
    return df[QUEUE_COLS].reset_index(drop=True)


def write_evidence(signals: dict[str, Signals], out_jsonl) -> None:
    """reports/evidence_<model_version>.jsonl: mỗi dòng {image_id, boxes: [{obj_id, box, note, signal}]},
    để API/extension tô box nghi vấn. Đi kèm ranked_queue, không đổi quy ước 3."""
    raise NotImplementedError("TODO(Cường): gom evidence của mọi tín hiệu theo image_id")
