"""Quy ước 1: mọi tín hiệu rủi ro trả về {image_id: SignalResult} cho MỌI ảnh (kể cả value=0)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SignalResult:
    name: str
    value: float  # [0, 1], đã chuẩn hoá để trọng số trong configs/weights.yaml so sánh được
    reason: str = ""  # tiếng Việt, có con số: "Box car #12 cao 9px, nhỏ hơn 99% car khác"
    evidence: list[dict] = field(default_factory=list)  # [{obj_id, box, note}] để giao diện tô box

    def __post_init__(self):
        if not 0.0 <= self.value <= 1.0:
            raise ValueError(f"{self.name}: value={self.value} nằm ngoài [0, 1]")
        if self.value > 0 and not any(ch.isdigit() for ch in self.reason):
            raise ValueError(f"{self.name}: reason phải có con số, nhận được {self.reason!r}")


Signals = dict[str, SignalResult]  # image_id -> SignalResult
