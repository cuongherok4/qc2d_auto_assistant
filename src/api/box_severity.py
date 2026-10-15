"""Mức độ của từng box evidence để tô màu cho reviewer: error (đỏ) hoặc review (vàng).

error: vi phạm luật guideline đã duyệt, hoặc detector bất đồng (thiếu nhãn / sai class)
với độ tin cậy ≥ error_conf. Mọi box còn lại (box lệch, nhãn không có dự đoán, conf thấp,
tín hiệu hình học) là review. Ngưỡng nằm ở configs/review.yaml, mục box_severity.
"""

from __future__ import annotations

import re

CONF = re.compile(r"\bmodel: .+ (\d+(?:\.\d+)?)$")


def _conf(box: dict) -> float | None:
    match = CONF.search(box.get("note") or "")
    return float(match.group(1)) if match else None


def annotate(boxes: list[dict], policy: dict) -> list[dict]:
    """Trả bản sao evidence kèm 'severity'; cặp nhãn + model liền nhau dùng chung conf của model."""
    always = set(policy.get("error_signals", []))
    conf_signals = set(policy.get("error_conf_signals", []))
    threshold = float(policy.get("error_conf", 1.0))
    out = []
    for i, box in enumerate(boxes):
        signal = box.get("signal")
        conf = _conf(box)
        nxt = boxes[i + 1] if i + 1 < len(boxes) else None
        if conf is None and box.get("obj_id") is not None and nxt and nxt.get("obj_id") is None \
                and nxt.get("signal") == signal:
            conf = _conf(nxt)
        error = signal in always or (signal in conf_signals and conf is not None and conf >= threshold)
        out.append({**box, "severity": "error" if error else "review"})
    return out
