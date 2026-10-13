"""Mốc 4 · VLM xem lại top 30% hàng đợi theo visual_rules của spec. Phụ trách: Sơn.
Hướng dẫn: skill `guideline-rules` (visual_rules) và `qc-signals`.

Chỉ chạy trên top 30%, câu hỏi đóng từ spec. Phần mở rộng: cắt đầu tiên nếu trễ.
Trả về SignalResult name="vlm", reason dẫn rule ID: "[V1] VLM: vật trong box là đèn xe".
"""

from __future__ import annotations


def vlm_check(objects, images, spec: dict, top_ids: list[str]):
    raise NotImplementedError("TODO(Cường): hỏi VLM local (Qwen2.5-VL) theo visual_rules")
