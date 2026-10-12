"""Adapter for the team's ML backend; never simulates successful training."""

from __future__ import annotations

import hashlib
import importlib
import io
import math
import threading
from pathlib import Path

import pandas as pd
from fastapi import HTTPException

from src import contracts


class ModelManager:
    def __init__(self, settings, store, service, backend=None):
        self.settings, self.store, self.service = settings, store, service
        self.backend = backend
        self.backend_error = None
        self.lock = service.activation_lock
        if backend is None and settings.retrain_backend:
            try:
                module, name = settings.retrain_backend.split(":", 1)
                self.backend = getattr(importlib.import_module(module), name)
                if not callable(self.backend):
                    raise TypeError("Backend phải là callable")
            except (ImportError, AttributeError, ValueError, TypeError) as exc:
                self.backend_error = str(exc)

    def info(self):
        frame, queue_id, path = self.service.snapshot()
        last = self.store.state("training") or {}
        watermark = last.get("watermark", 0)
        rows = [row for row in self.store.records() if row["id"] > watermark]
        latest = {row["image_id"]: row for row in rows}
        count = sum(row["verdict"] != "skip" for row in latest.values())
        return {
            "model_version": str(frame.model_version.iloc[0]) if len(frame) else None,
            "queue_id": queue_id,
            "queue_file": str(path) if path else None,
            "backend_ready": self.backend is not None,
            "backend_error": self.backend_error,
            "new_labeled_images": count,
            "new_verdicts": sum(row["verdict"] != "skip" for row in rows),
            "retrain_after": self.settings.retrain_after,
            "gate": {"split": "val", "metric": "recall@20%", "max_drop": self.settings.max_recall_drop},
            "last_training": last,
            "versions": list((self.store.state("versions") or {}).keys()),
        }

    def maybe_retrain(self):
        last = self.store.state("training") or {}
        since = last.get("attempted_through", last.get("watermark", 0))
        fresh = sum(row["id"] > since and row["verdict"] != "skip" for row in self.store.records())
        if self.backend and fresh >= self.settings.retrain_after:
            threading.Thread(target=self._automatic, daemon=True, name="m13-retrain").start()

    def _automatic(self):
        try:
            self.retrain()
        except HTTPException:
            pass  # Failure retained in /model; /verdict does not report fake training success.

    def retrain(self):
        if self.backend is None:
            raise HTTPException(503, "Backend ML chưa tích hợp; src/scoring/gbm.py vẫn là stub")
        if not self.lock.acquire(blocking=False):
            raise HTTPException(409, "Đang học lại")
        try:
            info = self.info()
            if info["new_verdicts"] < self.settings.retrain_after:
                message = f"Cần {self.settings.retrain_after} verdict mới, không tính skip/retry"
                raise HTTPException(409, message)
            history = self.store.records()
            previous = self.store.state("training") or {}
            watermark = previous.get("watermark", 0)
            attempted = max(row["id"] for row in history)
            latest = {row["image_id"]: row for row in history if row["id"] > watermark}
            labels = [row for row in latest.values() if row["verdict"] != "skip"]
            if not labels:
                raise HTTPException(409, "Không còn nhãn hợp lệ sau khi lấy verdict mới nhất theo ảnh")
            self.store.state(
                "training", {"status": "running", "watermark": watermark, "attempted_through": attempted}
            )
            old_model = self.store.state("model") or {}
            if info["queue_file"]:
                self.store.state(
                    "model",
                    {
                        **old_model,
                        "model_version": info["model_version"],
                        "queue_file": info["queue_file"],
                        "queue_id": info["queue_id"],
                    },
                )
            try:
                candidate = self.backend(
                    verdicts=labels,
                    current_model=info["model_version"],
                    seed=self.settings.audit_seed,
                    validation_split="val",
                    top_fraction=0.2,
                )
                version = str(candidate["model_version"])
                if (
                    not version
                    or version == info["model_version"]
                    or version in (self.store.state("versions") or {})
                ):
                    raise ValueError("Backend cần trả model_version mới")
                if candidate["validation_split"] != "val" or candidate["metric"] != "recall@20%":
                    raise ValueError("Gate cần metric recall@20% đo trên split val")
                splits = candidate["split_manifest"]
                if set(splits) != {"train", "val", "test"}:
                    raise ValueError("Backend cần manifest train/val/test theo image_id")
                for ids in splits.values():
                    if (
                        not isinstance(ids, list)
                        or not ids
                        or any(not isinstance(i, str) or not i for i in ids)
                        or len(set(ids)) != len(ids)
                    ):
                        raise ValueError("Mỗi split cần danh sách image_id không rỗng/không trùng")
                train, val, test = (set(splits[k]) for k in ("train", "val", "test"))
                if train & val or train & test or val & test:
                    raise ValueError("Ảnh bị rò rỉ giữa train/val/test")
                if not {row["image_id"] for row in labels}.issubset(train):
                    raise ValueError("Verdict đưa vào training phải thuộc split train")
                before, after = float(candidate["recall_before"]), float(candidate["recall_after"])
                if any(not math.isfinite(n) or not 0 <= n <= 1 for n in (before, after)):
                    raise ValueError("Recall phải trong [0,1]")
                path = Path(candidate["queue_file"]).resolve()
                if info["queue_file"] and path == Path(info["queue_file"]).resolve():
                    raise ValueError("Backend phải ghi queue mới; không được ghi đè queue đang phục vụ")
                raw = path.read_bytes()
                frame = pd.read_csv(io.BytesIO(raw), dtype={"image_id": str, "model_version": str})
                errors = contracts.check_queue(frame)
                if frame.empty or set(frame.model_version) != {version} or errors:
                    raise ValueError(f"Queue của model mới không hợp lệ: {errors}")
                passed = after + self.settings.max_recall_drop + 1e-12 >= before
                result = {
                    "status": "accepted" if passed else "rejected",
                    "model_version": version,
                    "recall_before": before,
                    "recall_after": after,
                    "watermark": max(row["id"] for row in history),
                    "attempted_through": attempted,
                    "split_manifest": splits,
                }
                if passed:
                    versions = self.store.state("versions") or {}
                    if info["queue_file"] and info["model_version"]:
                        versions.setdefault(
                            info["model_version"],
                            {
                                **old_model,
                                "queue_file": info["queue_file"],
                                "queue_id": info["queue_id"],
                            },
                        )
                        if (
                            "evidence_file" not in versions[info["model_version"]]
                            and self.settings.evidence_file
                        ):
                            versions[info["model_version"]]["evidence_file"] = str(
                                self.settings.evidence_file
                            )
                    digest = hashlib.sha256(raw).hexdigest()
                    versions[version] = {"queue_file": str(path), "queue_id": digest}
                    # A new queue never inherits evidence computed for an older version.
                    evidence = Path(
                        candidate.get("evidence_file")
                        or path.with_name(path.stem.replace("ranked_queue_", "evidence_") + ".jsonl")
                    )
                    versions[version]["evidence_file"] = str(evidence)
                    if evidence.exists():
                        versions[version]["evidence_sha256"] = hashlib.sha256(
                            evidence.read_bytes()
                        ).hexdigest()
                    self.store.states(
                        {
                            "versions": versions,
                            "model": {"model_version": version, **versions[version]},
                            "training": result,
                        }
                    )
                else:
                    self.store.state("training", result)
                return result
            except Exception as exc:
                self.store.state(
                    "training",
                    {
                        "status": "failed",
                        "watermark": watermark,
                        "attempted_through": attempted,
                        "error": "Backend/artifact ML lỗi; phiên bản đang phục vụ được giữ",
                    },
                )
                raise HTTPException(503, "Backend học lại lỗi; xem /model.last_training") from exc
        finally:
            self.lock.release()

    def rollback(self, version):
        if not self.lock.acquire(blocking=False):
            raise HTTPException(409, "Đang học lại")
        try:
            candidate = (self.store.state("versions") or {}).get(version)
            if candidate is None:
                raise HTTPException(404, "Chưa có phiên bản đã được chấp nhận này")
            try:
                raw = Path(candidate["queue_file"]).read_bytes()
                frame = pd.read_csv(io.BytesIO(raw), dtype={"model_version": str})
                if frame.empty or contracts.check_queue(frame) or set(frame.model_version) != {version}:
                    raise ValueError("Queue lưu trữ không còn hợp lệ")
                if hashlib.sha256(raw).hexdigest() != candidate["queue_id"]:
                    raise ValueError("Queue lưu trữ đã đổi nội dung")
                if (
                    candidate.get("evidence_sha256")
                    and hashlib.sha256(Path(candidate["evidence_file"]).read_bytes()).hexdigest()
                    != candidate["evidence_sha256"]
                ):
                    raise ValueError("Evidence lưu trữ đã đổi nội dung")
            except (OSError, ValueError, TypeError) as exc:
                raise HTTPException(503, str(exc)) from exc
            self.store.state("model", {"model_version": version, **candidate})
            return {"status": "rolled_back", "model_version": version}
        finally:
            self.lock.release()
