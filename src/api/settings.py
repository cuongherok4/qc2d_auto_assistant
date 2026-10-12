"""Local configuration, injectable paths for tests and per-machine installations."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from src import config


@dataclass
class Settings:
    reports: Path = field(default_factory=lambda: config.path("reports_dir"))
    database: Path = field(default_factory=lambda: config.path("review_db"))
    images: Path = field(default_factory=lambda: config.path("images_dir"))
    predictions: Path = field(default_factory=lambda: config.path("preds_parquet"))
    mapping: Path = field(default_factory=lambda: config.path("cvat_map"))
    cvat_url: str = field(default_factory=lambda: config.load("paths")["cvat_url"])
    queue_file: Path | None = None
    queue_batches: dict[str, str] = field(default_factory=dict)
    evidence_file: Path | None = None
    audit_every: int = 10
    audit_seed: int = 42
    retrain_after: int = 50
    max_recall_drop: float = 0.005
    rank_buckets: tuple[float, ...] = (0.2, 0.5, 1.0)
    allowed_origins: tuple[str, ...] = ()
    server_host: str = "127.0.0.1"
    server_port: int = 8000
    fixture_dir: str = "data/samples/review"
    retrain_backend: str | None = None
    recheck_backend: str | None = None
    snapshot_dir: str = "data/cvat-snapshots"
    recheck_dir: str = "data/rechecks"
    data_purpose: str = "development"

    @classmethod
    def configured(cls) -> Settings:
        values = config.load("review").copy()
        for key in ("queue_file", "evidence_file"):
            value = os.environ.get(f"M13_{key.upper()}", values.get(key))
            values[key] = config.ROOT / value if value else None
        for key in ("images", "database", "reports", "mapping", "predictions"):
            if value := os.environ.get(f"M13_{key.upper()}"):
                values[key] = config.ROOT / value
        if value := os.environ.get("M13_CVAT_URL"):
            values["cvat_url"] = value
        for key in ("recheck_backend", "data_purpose", "snapshot_dir", "recheck_dir"):
            if value := os.environ.get(f"M13_{key.upper()}"):
                values[key] = value
        return cls(**values)
