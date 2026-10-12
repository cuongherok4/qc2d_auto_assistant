"""CLI helpers for running, packaging and exporting measured review sessions."""

from __future__ import annotations

import csv
import json
import os
import platform
import shutil
import socket
import zipfile
from pathlib import Path

from fastapi import HTTPException

from src import config
from src.api.pilot import session_key
from src.api.saved_labels import SavedLabels
from src.api.service import QueueService
from src.api.settings import Settings
from src.api.store import ReviewStore


def doctor(*, verify_cvat=False) -> dict:
    settings = Settings.configured()
    paths = {"images": settings.images, "predictions": settings.predictions, "cvat_map": settings.mapping}
    source = Path(os.environ.get("M13_CVAT_SOURCE", str(config.ROOT.parent / "cvat-lidar-autoqc/cvat-day2")))
    address = settings.cvat_url.split("//", 1)[-1].split("/", 1)[0]
    host, _, port = address.partition(":")
    try:
        with socket.create_connection((host, int(port or 80)), timeout=1):
            cvat = True
    except OSError:
        cvat = False
    service = QueueService(settings, ReviewStore(settings.database))
    mapping, warnings = service.mapping()
    verification = {"checked_images": 0, "errors": [], "requested": verify_cvat}
    if verify_cvat:
        reader = SavedLabels(settings, service)
        try:
            frame, queue_id, _ = service.snapshot()
            for image_id in frame.image_id:
                try:
                    reader.capture(image_id, queue_id=queue_id)
                    verification["checked_images"] += 1
                except HTTPException as exc:
                    verification["errors"].append({"image_id": image_id, "detail": exc.detail})
        except HTTPException as exc:
            verification["errors"].append({"detail": exc.detail})
    return {
        "machine": {
            "hostname": socket.gethostname(),
            "system": platform.system(),
            "python": platform.python_version(),
        },
        "paths": {key: {"path": str(path), "exists": path.exists()} for key, path in paths.items()},
        "cvat_source": {"path": str(source), "exists": (source / "docker-compose.yml").exists()},
        "docker": shutil.which("docker"),
        "cvat_listening": cvat,
        "credentials_present": {
            key: bool(os.environ.get(key)) for key in ("CVAT_USER", "CVAT_PASSWORD", "GEMINI_API_KEY")
        },
        "free_disk_gib": round(shutil.disk_usage(config.ROOT).free / 1024**3, 1),
        "mapping": {"entries": len(mapping), "warnings": warnings, "cvat_readonly": verification},
    }


def package_extension(output: Path) -> int:
    source = config.ROOT / "extension"
    output.parent.mkdir(parents=True, exist_ok=True)
    files = [p for p in source.iterdir() if p.suffix in {".json", ".js", ".html", ".css", ".md"}]
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for file in sorted(files):
            archive.write(file, file.name)
    return len(files)


def export_pilot(
    output: Path,
    *,
    reviewer: str | None = None,
    session_id: str | None = None,
    include_development: bool = False,
) -> dict:
    """Export only observed DB events. No synthetic times or extrapolated measurements."""
    store = ReviewStore(Settings.configured().database)
    records = store.records(reviewer=reviewer, session_id=session_id)
    excluded = 0
    if not include_development:
        eligible = []
        for row in records:
            manifest = store.state(session_key(row["reviewer"], row["session_id"])) or {}
            plan = manifest.get("plan", {})
            if (
                manifest.get("purpose") == "human_pilot"
                and manifest.get("human_confirmed")
                and row["queue_id"] == manifest.get("queue_id")
                and row["review_order"] == plan.get("order")
            ):
                eligible.append(row)
            else:
                excluded += 1
        records = eligible
    output.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "id",
        "request_id",
        "image_id",
        "verdict",
        "reviewer",
        "seconds_spent",
        "note",
        "obj_ids",
        "created_at",
        "batch_id",
        "queue_id",
        "model_version",
        "rank",
        "is_audit",
        "session_id",
        "review_order",
    ]
    with output.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        for row in records:
            writer.writerow({**row, "obj_ids": json.dumps(row["obj_ids"], ensure_ascii=False)})
    groups = {}
    for row in records:
        key = (row["reviewer"], row["session_id"], row["queue_id"], row["review_order"])
        groups.setdefault(key, []).append(row)
    summary = []
    for key, rows in groups.items():
        seconds = sum(row["seconds_spent"] for row in rows)
        latest = {row["image_id"]: row for row in rows}
        errors = sum(row["verdict"] == "error" for row in latest.values())
        summary.append(
            {
                "reviewer": key[0],
                "session_id": key[1],
                "queue_id": key[2],
                "order": key[3],
                "images": len(latest),
                "events": len(rows),
                "seconds": seconds,
                "true_errors": errors,
                "latest_verdicts": {
                    v: sum(row["verdict"] == v for row in latest.values())
                    for v in ("error", "false_alarm", "skip")
                },
                "errors_per_hour": errors * 3600 / seconds if seconds else None,
                "pilot_manifest": None if include_development else store.state(session_key(key[0], key[1])),
            }
        )
    result = {
        "source": str(store.path),
        "events": len(records),
        "excluded_events": excluded,
        "include_development": include_development,
        "sessions": summary,
        "note": "Đây là export dữ liệu đã lưu, chưa tự xác nhận nghiệm thu pilot thật.",
    }
    output.with_suffix(".summary.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return result
