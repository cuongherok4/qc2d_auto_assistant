"""Persist CVAT inputs and publish a new queue only after the team's backend validates it."""

from __future__ import annotations

import hashlib
import importlib
import inspect
import io
import json
from pathlib import Path
from uuid import uuid4

import pandas as pd
from fastapi import HTTPException

from src import config, contracts
from src.api.saved_labels import atomic_json
from src.api.schemas import Evidence


class RecheckManager:
    def __init__(self, settings, store, service, saved, backend=None):
        self.settings, self.store, self.service, self.saved = settings, store, service, saved
        self.backend, self.backend_error = backend, None
        # One API process per DB. A running entry cannot survive that process's restart.
        for key, value in store.state_items("recheck:").items():
            if value["status"] == "running":
                store.state(
                    key,
                    {
                        **value,
                        "status": "failed",
                        "error": "Tiến trình API bị ngắt; queue chưa activate, đọc nguồn và tạo yêu cầu mới",
                    },
                )
        if backend is None and settings.recheck_backend:
            try:
                module, name = settings.recheck_backend.split(":", 1)
                self.backend = getattr(importlib.import_module(module), name)
                if not callable(self.backend):
                    raise TypeError("Backend phải callable")
            except (ImportError, AttributeError, ValueError, TypeError) as exc:
                self.backend, self.backend_error = None, str(exc)
        self.uses_manifest = False
        if self.backend is not None:
            try:
                self.uses_manifest = "manifest_file" in inspect.signature(self.backend).parameters
            except (TypeError, ValueError):
                pass  # Legacy callables continue to receive the existing adapter arguments.

    def pilot_snapshot(self, queue_id):
        return any(
            row.get("purpose") == "human_pilot" and row.get("queue_id") == queue_id
            for row in self.store.state_items("pilot:").values()
        )

    def readiness(self, queue_path, batch=None, queue_id=None):
        if self.backend is None:
            return False, "Chưa có backend QC cho queue này; điểm chưa thay đổi."
        if batch is not None:
            return False, "Batch phụ chưa hỗ trợ kiểm tra lại; cần phục vụ batch như queue chính"
        if queue_id and self.pilot_snapshot(queue_id):
            return False, "Queue đang dùng cho pilot; giữ snapshot, chấm lại bằng DB review riêng"
        if self.uses_manifest and (
            queue_path is None or not queue_path.with_suffix(".manifest.json").is_file()
        ):
            return False, "Queue thiếu manifest từ lệnh rank; chưa thể kiểm tra lại lỗi"
        return True, "Có thể kiểm tra lại lỗi từ nhãn đã Save."

    def capture(self, image_id, batch=None, queue_id=None):
        result = self.saved.capture(image_id, batch, queue_id)
        payload = result.pop("payload")
        result.pop("snapshot_file")
        _, current_id, queue_path = self.service.snapshot(batch)
        if current_id != result["queue_id"]:
            raise HTTPException(409, "Queue đã đổi trong lúc đọc nhãn; tải lại")
        ready, message = self.readiness(queue_path, batch, current_id)
        return {
            **result,
            "image_id": image_id,
            "annotation_version": payload["annotation_version"],
            "boxes": payload["boxes"],
            "box_count": len(payload["boxes"]),
            "backend_ready": ready,
            "backend_message": message,
            "source": "CVAT API: nhãn đã Save; không bao gồm thay đổi chưa lưu trên canvas",
        }

    def status(self, request_id):
        row = self.store.state(f"recheck:{request_id}")
        if row is None:
            raise HTTPException(404, "Chưa có yêu cầu kiểm tra lại này")
        return row

    def run(self, image_id, value):
        identity = {"image_id": image_id, **value}
        key = f"recheck:{value['request_id']}"
        previous = self.store.state(key)
        if previous:
            if previous["input"] != identity:
                raise HTTPException(409, "request_id kiểm tra lại đã dùng cho nội dung khác")
            if previous["status"] == "completed":
                return previous["result"]
            raise HTTPException(409, "Yêu cầu đã chạy; xem trạng thái trước khi tạo yêu cầu mới")
        if self.backend is None:
            raise HTTPException(503, "Backend QC chưa tích hợp; chưa đổi điểm/queue")
        if not self.service.activation_lock.acquire(blocking=False):
            raise HTTPException(409, "Đang học lại hoặc tái kiểm tra; thử lại sau")
        output = None
        try:
            frame, before_id, before_path = self.service.snapshot()
            if before_id != value["queue_id"]:
                raise HTTPException(409, "Queue đã đổi; tải lại trước khi kiểm tra")
            ready, message = self.readiness(before_path, queue_id=before_id)
            if not ready:
                raise HTTPException(409 if self.pilot_snapshot(before_id) else 503, message)
            captured = self.saved.capture(image_id, queue_id=before_id)
            if captured["snapshot_id"] != value["snapshot_id"]:
                raise HTTPException(409, "Nhãn CVAT đã đổi; đọc nhãn đã Save lại trước khi kiểm tra")
            version = f"recheck-{uuid4().hex}"
            output = (config.ROOT / self.settings.recheck_dir / version).resolve()
            output.mkdir(parents=True, exist_ok=False)
            manifest = {
                "status": "running",
                "input": identity,
                "snapshot_file": captured["snapshot_file"],
                "previous_queue_id": before_id,
            }
            atomic_json(output / "input.json", captured)
            self.store.state(key, manifest)
            result = self.backend(
                snapshot=json.loads(json.dumps(captured["payload"])),
                queue=frame.copy(deep=True),
                output_dir=output,
                model_version=version,
                seed=self.settings.audit_seed,
                **({"manifest_file": before_path.with_suffix(".manifest.json")}
                   if self.uses_manifest else {}),
            )
            paths = {name: Path(result[name]).resolve() for name in ("queue_file", "evidence_file")}
            if any(not path.is_relative_to(output) for path in paths.values()):
                raise ValueError("Backend phải ghi artifact mới trong output_dir, không ghi đè queue cũ")
            raw = paths["queue_file"].read_bytes()
            candidate = pd.read_csv(io.BytesIO(raw), dtype={"image_id": str, "model_version": str}).fillna(
                {"top_reasons": ""}
            )
            errors = contracts.check_queue(candidate)
            if errors or candidate.empty or set(candidate.image_id) != set(frame.image_id):
                raise ValueError(f"Queue phải hợp lệ và giữ đúng tập ảnh: {errors}")
            if set(candidate.model_version) != {version}:
                raise ValueError("Backend phải dùng model_version được cấp")
            evidence = [
                json.loads(line) for line in paths["evidence_file"].read_text().splitlines() if line.strip()
            ]
            if len({row["image_id"] for row in evidence}) != len(evidence):
                raise ValueError("Evidence có image_id trùng")
            if {row["image_id"] for row in evidence} != set(frame.image_id):
                raise ValueError("Evidence cần một dòng cho mỗi ảnh, kể cả boxes rỗng")
            for row in evidence:
                for box in row["boxes"]:
                    Evidence.model_validate(box)
                    points = box["box"]
                    if not all(pd.notna(n) and float("-inf") < float(n) < float("inf") for n in points):
                        raise ValueError("Evidence có toạ độ không hữu hạn")
                    if points[2] <= points[0] or points[3] <= points[1]:
                        raise ValueError("Evidence có box đảo chiều")
            # Re-read serving data after backend work. Existing snapshots must remain unchanged.
            _, current_id, _ = self.service.snapshot()
            if current_id != before_id:
                raise ValueError("Queue đang phục vụ đổi trong lúc kiểm tra; chưa activate")
            if self.saved.capture(image_id, queue_id=before_id)["snapshot_id"] != captured["snapshot_id"]:
                raise ValueError("Nhãn CVAT đổi trong lúc backend chạy; cần kiểm tra lại nguồn mới")
            digest = hashlib.sha256(raw).hexdigest()
            active = {
                "model_version": version,
                "queue_id": digest,
                "queue_file": str(paths["queue_file"]),
                "evidence_file": str(paths["evidence_file"]),
                "evidence_sha256": hashlib.sha256(paths["evidence_file"].read_bytes()).hexdigest(),
            }
            old = self.store.state("model") or {}
            versions = self.store.state("versions") or {}
            if before_path and len(frame):
                old_evidence = self.settings.evidence_file or before_path.with_name(
                    before_path.stem.replace("ranked_queue_", "evidence_") + ".jsonl"
                )
                previous = {
                    "queue_file": str(before_path),
                    "queue_id": before_id,
                    "evidence_file": old.get("evidence_file") or str(old_evidence),
                }
                if Path(previous["evidence_file"]).is_file():
                    previous["evidence_sha256"] = hashlib.sha256(
                        Path(previous["evidence_file"]).read_bytes()
                    ).hexdigest()
                versions.setdefault(str(frame.model_version.iloc[0]), previous)
            versions[version] = {k: v for k, v in active.items() if k != "model_version"}
            before_row = frame[frame.image_id == image_id].iloc[0]
            after_row = candidate[candidate.image_id == image_id].iloc[0]
            public = {
                "status": "completed",
                "request_id": value["request_id"],
                "image_id": image_id,
                "snapshot_id": value["snapshot_id"],
                "previous_queue_id": before_id,
                "queue_id": digest,
                "model_version": version,
                "risk_before": float(before_row.risk_score),
                "risk_after": float(after_row.risk_score),
                "score_changed": float(before_row.risk_score) != float(after_row.risk_score),
            }
            manifest.update(status="completed", result=public)
            atomic_json(output / "result.json", manifest)
            self.store.states({"model": active, "versions": versions, key: manifest})
            return public
        except HTTPException:
            current = self.store.state(key)
            if current and current["status"] == "running":
                self.store.state(
                    key,
                    {
                        "status": "failed",
                        "input": identity,
                        "error": "Kiểm tra lại bị từ chối; queue chưa activate",
                    },
                )
            raise
        except Exception as exc:
            self.store.state(
                key,
                {
                    "status": "failed",
                    "input": identity,
                    "error": "Backend/artifact kiểm tra lại lỗi; queue chưa activate",
                },
            )
            raise HTTPException(503, "Kiểm tra lại thất bại; queue/verdict cũ được giữ") from exc
        finally:
            self.service.activation_lock.release()
