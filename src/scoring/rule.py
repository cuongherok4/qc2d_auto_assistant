"""Bước 4 · Chấm điểm rule: risk = 100 * sum(w * value) / sum(w), top 3 lý do theo w * value.
Phụ trách: Cường. Hướng dẫn: skill `risk-scoring`.

Đầu ra đúng quy ước 3 (src/contracts.py: QUEUE_COLS). Hoà điểm xếp theo image_id để kết quả xác định.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd

from src.contracts import IMG_H, IMG_W, QUEUE_COLS, REASON_SEP
from src.features.base import Signals


def rank(signals: dict[str, Signals], weights: dict[str, float], model_version: str,
         top_k: int = 3) -> pd.DataFrame:
    """signals: {tên tín hiệu: {image_id: SignalResult}}. Tín hiệu không có trọng số bị bỏ qua."""
    used = {n: s for n, s in signals.items() if weights.get(n, 0) > 0}
    if not used:
        raise ValueError("Không có tín hiệu nào có trọng số trong configs/weights.yaml")
    total_w = sum(weights[n] for n in used)
    image_ids = sorted(set().union(*(s.keys() for s in used.values())))
    if not math.isfinite(total_w):
        raise ValueError("Trọng số không hữu hạn")
    if any(set(s) != set(image_ids) for s in used.values()):
        raise ValueError("Mỗi tín hiệu phải bao phủ đúng toàn bộ image_id")
    if not 1 <= top_k <= 3:
        raise ValueError("top_k phải từ 1 đến 3")
    rows = []
    for img in image_ids:
        contrib = [(weights[n] * s[img].value, s[img].reason) for n, s in used.items() if img in s]
        score = 100 * sum(c for c, _ in contrib) / total_w
        reasons = [r for c, r in sorted(contrib, key=lambda x: -x[0]) if c > 0 and r][:top_k]
        rows.append({"image_id": img, "risk_score": round(score, 2), "top_reasons": REASON_SEP.join(reasons)})
    df = pd.DataFrame(rows, columns=["image_id", "risk_score", "top_reasons"])
    df = df.sort_values(["risk_score", "image_id"], ascending=[False, True])
    df["rank"] = range(1, len(df) + 1)
    df["model_version"] = model_version
    return df[QUEUE_COLS].reset_index(drop=True)


def write_evidence(signals: dict[str, Signals], out_jsonl) -> None:
    """reports/evidence_<model_version>.jsonl: mỗi dòng {image_id, boxes: [{obj_id, box, note, signal}]},
    để API/extension tô box nghi vấn. Đi kèm ranked_queue, không đổi quy ước 3."""
    image_ids = sorted(set().union(*(s.keys() for s in signals.values())))
    if any(set(s) != set(image_ids) for s in signals.values()):
        raise ValueError("Evidence: tín hiệu không bao phủ cùng tập ảnh")
    rows = []
    for image_id in image_ids:
        boxes = []
        for name, values in sorted(signals.items()):
            result = values[image_id]
            if result.value <= 0:
                continue
            for source in result.evidence:
                box = [float(x) for x in source["box"]]
                if (len(box) != 4 or not all(math.isfinite(x) for x in box)
                        or not 0 <= box[0] < box[2] <= IMG_W
                        or not 0 <= box[1] < box[3] <= IMG_H):
                    raise ValueError(f"{image_id}: evidence có box không hợp lệ")
                boxes.append({"obj_id": None if source.get("obj_id") is None else str(source["obj_id"]),
                              "box": box, "note": source.get("note") or result.reason, "signal": name})
        rows.append({"image_id": image_id, "boxes": boxes})
    path = Path(out_jsonl)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False, allow_nan=False)+"\n" for r in rows),
                    encoding="utf-8")
