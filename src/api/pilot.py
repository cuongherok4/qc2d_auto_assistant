"""Explicit human pilot enrollment before measurement; automated sessions stay excluded."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field

from src.api.saved_labels import SavedLabels, atomic_json, canonical
from src.api.service import QueueService
from src.api.settings import Settings
from src.api.store import ReviewStore


class PilotPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    reviewer: str = Field(min_length=1, max_length=100)
    session_id: str = Field(min_length=1, max_length=100)
    comparison_id: str = Field(min_length=1, max_length=100)
    order: Literal["priority", "file"]
    design: Literal["parallel_reviewers"] = "parallel_reviewers"


def session_key(reviewer, session_id):
    return "pilot:" + hashlib.sha256(canonical([reviewer, session_id])).hexdigest()


def register(plan: PilotPlan, *, confirmed: bool, settings=None, saved=None) -> dict:
    settings = settings or Settings.configured()
    store = ReviewStore(settings.database)
    service = QueueService(settings, store)
    if not confirmed or settings.data_purpose != "real":
        raise ValueError("Pilot cần người review xác nhận --confirm-human và M13_DATA_PURPOSE=real")
    frame, queue_id, _ = service.snapshot()
    if frame.empty or any("fixture" in str(v).lower() for v in frame.model_version):
        raise ValueError("Không đăng ký dữ liệu fixture/queue rỗng làm pilot thật")
    identity = plan.model_dump()
    key = session_key(plan.reviewer, plan.session_id)
    previous = store.state(key)
    if previous:
        if previous["plan"] != identity:
            raise ValueError("Phiên đã đăng ký; không đổi thiết kế sau khi đo")
        return previous
    if store.records(reviewer=plan.reviewer, session_id=plan.session_id):
        raise ValueError("Không đổi phiên development/tự động có verdict sẵn thành pilot")
    # Parallel reviewers avoid showing the same images twice to one person.
    if any(row["queue_id"] == queue_id for row in store.records(reviewer=plan.reviewer)):
        raise ValueError("Reviewer đã xem batch này; chọn người chưa xem cho thiết kế parallel_reviewers")
    reader = saved or SavedLabels(settings, service)
    labels, tasks, captures = [], set(), {}
    mapping_digest = hashlib.sha256(settings.mapping.read_bytes()).hexdigest()
    for image_id in sorted(frame.image_id):
        try:
            captured = reader.capture(image_id, queue_id=queue_id)
        except HTTPException as exc:
            raise ValueError(f"Chưa đăng ký được pilot: {exc.detail}") from None
        captures[image_id] = captured["snapshot_id"]
        snapshot = captured["payload"]
        tasks.add((snapshot["cvat_origin"], snapshot["cvat"]["task_id"]))
        boxes = [{k: box[k] for k in ("category", "box", "attributes")} for box in snapshot["boxes"]]
        labels.append({"image_id": image_id, "boxes": sorted(boxes, key=canonical)})
    if any(
        reader.capture(image_id, queue_id=queue_id)["snapshot_id"] != digest
        for image_id, digest in captures.items()
    ):
        raise ValueError("Nhãn ban đầu đổi trong lúc đăng ký; chưa bắt đầu pilot")
    if hashlib.sha256(settings.mapping.read_bytes()).hexdigest() != mapping_digest:
        raise ValueError("Mapping đổi trong lúc đăng ký")
    manifest = {
        "purpose": "human_pilot",
        "human_confirmed": True,
        "plan": identity,
        "queue_id": queue_id,
        "model_version": str(frame.model_version.iloc[0]),
        "image_ids_sha256": hashlib.sha256(canonical(sorted(frame.image_id))).hexdigest(),
        "annotation_baseline_sha256": hashlib.sha256(canonical(labels)).hexdigest(),
        "mapping_sha256": mapping_digest,
        "cvat_tasks": sorted(tasks),
        "registered_at": datetime.now(UTC).isoformat(),
    }
    store.state(key, manifest)
    return manifest


def validate_verdict(store, settings, payload):
    manifest = store.state(session_key(payload["reviewer"], payload["session_id"]))
    if manifest is None:
        return  # Development remains usable; export excludes unregistered sessions.
    plan = manifest["plan"]
    if payload["queue_id"] != manifest["queue_id"] or payload["review_order"] != plan["order"]:
        raise HTTPException(409, "Pilot phải giữ nguyên snapshot/thứ tự đã đăng ký")
    if payload["batch_id"]:
        raise HTTPException(409, "Pilot dùng queue đã đăng ký, để batch trống")
    if (
        not settings.mapping.is_file()
        or hashlib.sha256(settings.mapping.read_bytes()).hexdigest() != manifest["mapping_sha256"]
    ):
        raise HTTPException(409, "Mapping pilot đã đổi; dừng đo và đăng ký phiên mới")


def compare(first: Path, second: Path, output: Path) -> dict:
    summaries = [json.loads(p.read_text()) for p in (first, second)]
    if any(s.get("include_development") or len(s["sessions"]) != 1 for s in summaries):
        raise ValueError("Chọn hai export chỉ có một phiên human_pilot mỗi file")
    arms = [s["sessions"][0] for s in summaries]
    manifests = [arm.get("pilot_manifest") or {} for arm in arms]
    if any(m.get("purpose") != "human_pilot" or not m.get("human_confirmed") for m in manifests):
        raise ValueError("Không dùng session tự động/development làm pilot")
    for arm, manifest in zip(arms, manifests, strict=True):
        if any(
            arm[key] != manifest["plan"][plan_key]
            for key, plan_key in (("reviewer", "reviewer"), ("session_id", "session_id"), ("order", "order"))
        ):
            raise ValueError("Summary không khớp phiên đã đăng ký")
    for field in ("queue_id", "image_ids_sha256", "annotation_baseline_sha256"):
        if manifests[0][field] != manifests[1][field]:
            raise ValueError(f"Hai lượt không cùng batch/snapshot/nhãn ban đầu: {field}")
    a, b = (m["plan"] for m in manifests)
    if a["comparison_id"] != b["comparison_id"] or {a["order"], b["order"]} != {"priority", "file"}:
        raise ValueError("Hai lượt phải cùng comparison_id và khác thứ tự priority/file")
    if a["reviewer"] == b["reviewer"]:
        raise ValueError("Thiết kế parallel_reviewers cần hai người khác nhau để tránh nhớ ảnh")
    if set(map(tuple, manifests[0]["cvat_tasks"])) & set(map(tuple, manifests[1]["cvat_tasks"])):
        raise ValueError("Hai lượt phải có task CVAT riêng, không dùng nhãn đã sửa ở lượt trước")
    result = {
        "comparison_id": a["comparison_id"],
        "queue_id": manifests[0]["queue_id"],
        "arms": arms,
        "note": (
            "Số liệu mô tả từ người thật; tốc độ từng reviewer vẫn là yếu tố gây nhiễu. "
            "Cần thêm các batch đối trọng trước khi kết luận hiệu quả."
        ),
    }
    atomic_json(output, result)
    return result
