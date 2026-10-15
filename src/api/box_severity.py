"""Mức độ và tên lỗi của từng box evidence để reviewer biết box nào lỗi gì.

severity: error (đỏ) khi vi phạm luật guideline đã duyệt, hoặc detector bất đồng (thiếu nhãn /
sai class) với độ tin cậy ≥ error_conf; mọi box còn lại là review (vàng). Ngưỡng nằm ở
configs/review.yaml, mục box_severity.
issue: tên lỗi ngắn tiếng Việt. secondary: box model đi kèm box nhãn ngay trước nó (cùng một lỗi).
"""

from __future__ import annotations

import re

MODEL = re.compile(r"^model: (.+) (\d+(?:\.\d+)?)$")
LABEL = re.compile(r"^nhãn: (.+)$")


def _model(box: dict | None) -> tuple[str, float] | None:
    match = MODEL.match((box or {}).get("note") or "")
    return (match.group(1), float(match.group(2))) if match else None


def _iou(a: list[float], b: list[float]) -> float:
    w = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    h = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - w * h
    return w * h / union if union > 0 else 0.0


def _issue(box: dict, model: tuple[str, float] | None, partner: dict | None) -> str:
    signal, note = box.get("signal"), box.get("note") or ""
    if signal == "model_missing_label" and model:
        return f"Thiếu nhãn {model[0]} (model {model[1]:.2f})"
    if signal == "model_class_conflict" and model:
        label = LABEL.match(note)
        return f"Sai class: nhãn {label.group(1) if label else '?'} → model {model[0]} ({model[1]:.2f})"
    if signal == "model_loose_box" and model and partner:
        return f"Box lệch: IoU {_iou(box['box'], partner['box']):.2f} so với model {model[0]}"
    if signal == "label_unsupported":
        return "Box thừa? Model không thấy vật nào ở đây"
    return note or signal or "Box nghi vấn"


def _paired(label: dict | None, model: dict | None) -> bool:
    return bool(label and model) and label.get("obj_id") is not None and model.get("obj_id") is None \
        and label.get("signal") == model.get("signal")


def annotate(boxes: list[dict], policy: dict) -> list[dict]:
    """Trả bản sao evidence kèm severity, issue, secondary; cặp nhãn + model dùng chung conf của model."""
    always = set(policy.get("error_signals", []))
    conf_signals = set(policy.get("error_conf_signals", []))
    threshold = float(policy.get("error_conf", 1.0))
    out = []
    for i, box in enumerate(boxes):
        prev = boxes[i - 1] if i else None
        nxt = boxes[i + 1] if i + 1 < len(boxes) else None
        secondary = _paired(prev, box)
        partner = prev if secondary else nxt if _paired(box, nxt) else None
        model = _model(nxt) if partner is nxt and partner else _model(box)
        signal = box.get("signal")
        error = signal in always or (signal in conf_signals and model is not None and model[1] >= threshold)
        issue = f"Box model: {model[0]} {model[1]:.2f}" if secondary and model \
            else _issue(box, model, partner)
        out.append({**box, "severity": "error" if error else "review", "issue": issue,
                    "secondary": secondary})
    return out
