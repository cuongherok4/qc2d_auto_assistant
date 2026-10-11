"""Đọc config YAML. Mọi tham số (seed, trọng số, ngưỡng, đường dẫn) lấy từ configs/, không hard-code."""

from __future__ import annotations

from functools import cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "configs"


@cache
def load(name: str) -> dict:
    """load("weights") -> nội dung configs/weights.yaml."""
    with open(CONFIG_DIR / f"{name}.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def path(key: str) -> Path:
    """Đường dẫn tuyệt đối từ configs/paths.yaml, ví dụ path("labels_json")."""
    return ROOT / load("paths")[key]
