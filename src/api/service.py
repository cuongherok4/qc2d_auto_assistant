"""Queue snapshots and enrichment without changing the shared CSV contract."""

from __future__ import annotations

import hashlib
import io
import json
import math
import random
import re
import threading
from pathlib import Path

import pandas as pd
from fastapi import HTTPException

from src import config, contracts
from src.api.box_severity import annotate
from src.api.settings import Settings
from src.api.store import ReviewStore

IMAGE_ID = re.compile(r"^[\w.-]{1,200}$", re.ASCII)


def safe_id(value: str) -> str:
    if not IMAGE_ID.fullmatch(value) or value in {".", ".."}:
        raise HTTPException(422, "image_id không hợp lệ")
    return value


class QueueService:
    def __init__(self, settings: Settings, store: ReviewStore):
        self.settings, self.store = settings, store
        self._cache: dict = {}
        self.activation_lock = threading.Lock()

    def snapshot(self, batch: str | None = None) -> tuple[pd.DataFrame, str, Path | None]:
        active = self.store.state("model") or {}
        if batch:
            value = self.settings.queue_batches.get(batch)
            if not value:
                raise HTTPException(404, "Batch chưa có queue_batches trong configs/review.yaml")
            path = config.ROOT / value
        elif active.get("queue_file"):
            path = Path(active["queue_file"])
        elif self.settings.queue_file:
            path = self.settings.queue_file
        else:
            files = list(self.settings.reports.glob("ranked_queue_*.csv"))
            path = max(files, key=lambda p: (p.stat().st_mtime_ns, p.name)) if files else None
        if path is None:
            return pd.DataFrame(columns=contracts.QUEUE_COLS), "empty", None
        try:
            signature = (str(path.resolve()), path.stat().st_mtime_ns, path.stat().st_size)
            cached = self._cache.get(signature)
            if cached is None:
                raw = path.read_bytes()
                frame = pd.read_csv(io.BytesIO(raw), dtype={"image_id": str, "model_version": str}).fillna(
                    {"top_reasons": ""}
                )
                errors = contracts.check_queue(frame)
                if len(frame) and (frame["model_version"].isna().any() or frame["image_id"].isna().any()):
                    errors.append("image_id/model_version trống")
                for value in frame["image_id"]:
                    if not IMAGE_ID.fullmatch(value) or value in {".", ".."}:
                        errors.append("image_id không hợp lệ trong CSV")
                if errors:
                    raise ValueError("; ".join(errors))
                snapshot = (frame[contracts.QUEUE_COLS].sort_values("rank"), hashlib.sha256(raw).hexdigest())
                self._cache = {signature: snapshot}
                cached = snapshot
            frame, queue_id = cached
            if not batch and active.get("queue_id") and active["queue_id"] != queue_id:
                raise ValueError("Queue của model đang phục vụ đã đổi nội dung; cần phiên bản mới")
            return frame.copy(), queue_id, path
        except (OSError, ValueError, TypeError, KeyError, pd.errors.ParserError) as exc:
            raise HTTPException(503, f"Hàng đợi lỗi: {exc}") from exc

    def schedule(self, frame: pd.DataFrame) -> tuple[list[str], set[str]]:
        ids = frame["image_id"].tolist()
        halfway = math.ceil(len(ids) / 2)
        primary, lower = ids[:halfway], ids[halfway:]
        candidates = lower.copy()
        random.Random(self.settings.audit_seed).shuffle(candidates)
        result, audit = [], set()
        for index, image_id in enumerate(primary, 1):
            result.append(image_id)
            if self.settings.audit_every > 0 and index % self.settings.audit_every == 0 and candidates:
                selected = candidates.pop()
                result.append(selected)
                audit.add(selected)
        result.extend(image_id for image_id in lower if image_id not in audit)
        return result, audit

    def image_path(self, image_id: str) -> Path | None:
        safe_id(image_id)
        root = self.settings.images.resolve()
        candidates = (
            [root / image_id]
            if Path(image_id).suffix.lower() in {".jpg", ".jpeg", ".png"}
            else [root / f"{image_id}{suffix}" for suffix in (".jpg", ".jpeg", ".png")]
        )
        for path in candidates:
            if path.is_file() and path.resolve().is_relative_to(root):
                return path
        return None

    def evidence(self, path: Path | None, batch: str | None = None) -> tuple[dict, list[str]]:
        active = self.store.state("model") or {}
        active_evidence = (
            Path(active["evidence_file"])
            if active.get("evidence_file") and path and Path(active.get("queue_file", "")) == path
            else None
        )
        source = (
            active_evidence
            or (self.settings.evidence_file if batch is None else None)
            or (path.with_name(path.stem.replace("ranked_queue_", "evidence_") + ".jsonl") if path else None)
        )
        if source is None or not source.exists():
            return {}, ["Chưa có evidence từ pipeline"]
        try:
            items = {}
            raw = source.read_bytes()
            if (
                active_evidence
                and active.get("evidence_sha256")
                and hashlib.sha256(raw).hexdigest() != active["evidence_sha256"]
            ):
                raise ValueError("Evidence của snapshot đang phục vụ đã đổi nội dung")
            for line in raw.decode("utf-8").splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                if row["image_id"] in items:
                    raise ValueError("image_id trùng trong evidence")
                boxes = row["boxes"]
                if not isinstance(boxes, list):
                    raise ValueError("boxes cần là danh sách")
                for box in boxes:
                    coords = box["box"]
                    if len(coords) != 4 or any(not math.isfinite(float(n)) for n in coords):
                        raise ValueError("box evidence cần 4 toạ độ hữu hạn")
                    coords = box["box"] = [float(n) for n in coords]
                    if coords[2] <= coords[0] or coords[3] <= coords[1]:
                        raise ValueError("box evidence đảo chiều")
                    if box.get("obj_id") is not None:
                        box["obj_id"] = str(box["obj_id"])
                        if not IMAGE_ID.fullmatch(box["obj_id"]):
                            raise ValueError("obj_id evidence không hợp lệ")
                    if not isinstance(box.get("note", ""), str) or (
                        box.get("signal") is not None and not isinstance(box["signal"], str)
                    ):
                        raise ValueError("note/signal evidence cần là chuỗi")
                items[row["image_id"]] = boxes
            return items, []
        except (OSError, ValueError, KeyError, TypeError) as exc:
            return {}, [f"Evidence lỗi: {exc}"]

    def mapping(self) -> tuple[dict, list[str]]:
        if not self.settings.mapping.exists():
            return {}, ["Chưa đồng bộ CVAT local"]
        try:
            frame = pd.read_parquet(self.settings.mapping)
            if not {"image_id", "task_id", "job_id", "frame"}.issubset(frame.columns):
                raise ValueError("thiếu cột mapping")
            if frame.image_id.duplicated().any():
                raise ValueError("mapping mơ hồ: image_id trùng")
            if frame.duplicated(["task_id", "job_id", "frame"]).any():
                raise ValueError("mapping mơ hồ: nhiều ảnh cùng task/job/frame")
            result = {}
            for row in frame.to_dict("records"):
                if any(
                    int(row[k]) != row[k] or int(row[k]) < (0 if k == "frame" else 1)
                    for k in ("task_id", "job_id", "frame")
                ):
                    raise ValueError("task/job/frame không hợp lệ")
                result[str(row["image_id"])] = {
                    "task_id": int(row["task_id"]),
                    "job_id": int(row["job_id"]),
                    "frame": int(row["frame"]),
                }
            return result, []
        except (OSError, ValueError, TypeError, KeyError) as exc:
            return {}, [f"CVAT mapping lỗi: {exc}"]

    def enrich(self, row: dict, queue_id: str, batch: str | None, boxes: dict, mapping: dict) -> dict:
        image_id = row["image_id"]
        target = mapping.get(image_id)
        url = (
            None
            if target is None
            else (
                f"{self.settings.cvat_url.rstrip('/')}/tasks/{target['task_id']}/jobs/{target['job_id']}"
                f"?frame={target['frame']}"
            )
        )
        return {
            **row,
            "queue_id": queue_id,
            "batch_id": batch,
            "reasons": [r for r in str(row["top_reasons"]).split(contracts.REASON_SEP) if r],
            "evidence": annotate(boxes.get(image_id, []), self.settings.box_severity),
            "cvat_url": url,
            "cvat": target,
            "image_url": f"/image/{image_id}/file",
            "image_available": self.image_path(image_id) is not None,
        }

    def queue(
        self,
        *,
        batch=None,
        limit=50,
        offset=0,
        reviewer=None,
        session_id=None,
        include_reviewed=False,
        order="priority",
    ) -> dict:
        frame, queue_id, path = self.snapshot(batch)
        ids, _ = self.schedule(frame)
        if order == "file":
            ids = sorted(frame.image_id.tolist())
        reviewed = (
            set()
            if include_reviewed
            else {
                row["image_id"]
                for row in self.store.records(
                    queue_id=queue_id, reviewer=reviewer, session_id=session_id, review_order=order
                )
            }
        )
        remaining = [image_id for image_id in ids if image_id not in reviewed]
        boxes, evidence_warnings = self.evidence(path, batch)
        mapping, cvat_warnings = self.mapping()
        rows = frame.set_index("image_id", drop=False).to_dict("index")
        return {
            "items": [
                self.enrich(rows[k], queue_id, batch, boxes, mapping)
                for k in remaining[offset : offset + limit]
            ],
            "total": len(ids),
            "remaining": len(remaining),
            "reviewed": len(ids) - len(remaining),
            "offset": offset,
            "limit": limit,
            "queue_id": queue_id,
            "model_version": str(frame.model_version.iloc[0]) if len(frame) else None,
            "batch_id": batch,
            "warnings": evidence_warnings + cvat_warnings,
        }

    def detail(self, image_id: str, batch=None, queue_id=None) -> dict:
        safe_id(image_id)
        frame, current_id, path = self.snapshot(batch)
        if queue_id and queue_id != current_id:
            raise HTTPException(409, "Queue đã đổi; tải lại trước khi review")
        rows = frame[frame.image_id == image_id]
        if rows.empty:
            raise HTTPException(404, "Ảnh không thuộc hàng đợi")
        boxes, ew = self.evidence(path, batch)
        mapping, mw = self.mapping()
        result = self.enrich(rows.iloc[0].to_dict(), current_id, batch, boxes, mapping)
        result["warnings"] = ew + mw
        result["predictions"] = []
        if self.settings.predictions.exists():
            try:
                preds = pd.read_parquet(self.settings.predictions)
                errors = contracts.check_preds(preds)
                if errors:
                    raise ValueError("; ".join(errors))
                result["predictions"] = preds[preds.image_id == image_id].to_dict("records")
            except (OSError, ValueError, TypeError, KeyError) as exc:
                result["warnings"].append(f"Predictions lỗi: {exc}")
        return result

    def verdict_context(self, image_id: str, batch=None, queue_id=None):
        safe_id(image_id)
        frame, current_id, _ = self.snapshot(batch)
        if queue_id and queue_id != current_id:
            raise HTTPException(409, "Queue đã đổi; tải lại trước khi review")
        rows = frame[frame.image_id == image_id]
        if rows.empty:
            raise HTTPException(404, "Ảnh không thuộc hàng đợi")
        row = rows.iloc[0].to_dict()
        _, audit_ids = self.schedule(frame)
        return {"queue_id": current_id, "model_version": row["model_version"], "rank": row["rank"]}, (
            image_id in audit_ids
        )

    def stats(self, *, batch=None, reviewer=None, session_id=None, order=None, queue_id=None) -> dict:
        frame, current_id, _ = self.snapshot(batch)
        if queue_id and queue_id != current_id:
            if batch:
                raise HTTPException(422, "Chọn batch hoặc snapshot lịch sử, không chọn cả hai")
            saved = next(
                (v for v in (self.store.state("versions") or {}).values() if v["queue_id"] == queue_id),
                None,
            )
            if saved is None:
                raise HTTPException(404, "Không có snapshot lịch sử này")
            try:
                raw = Path(saved["queue_file"]).read_bytes()
                if hashlib.sha256(raw).hexdigest() != queue_id:
                    raise ValueError("Snapshot lịch sử đã đổi nội dung")
                frame = pd.read_csv(io.BytesIO(raw), dtype={"image_id": str, "model_version": str})
                if contracts.check_queue(frame):
                    raise ValueError("Snapshot lịch sử không hợp lệ")
            except (OSError, ValueError) as exc:
                raise HTTPException(503, str(exc)) from exc
        queue_id = queue_id or current_id
        history = self.store.records(
            queue_id=queue_id, reviewer=reviewer, session_id=session_id, review_order=order
        )
        latest = {row["image_id"]: row for row in history}

        def summarize(rows):
            counts = {
                key: sum(row["verdict"] == key for row in rows) for key in ("error", "false_alarm", "skip")
            }
            valid = counts["error"] + counts["false_alarm"]
            seconds = sum(row["seconds_spent"] for row in rows)
            return {
                "count": len(rows),
                "verdicts": counts,
                "error_rate": counts["error"] / valid if valid else None,
                "seconds_spent": seconds,
                "mean_seconds": seconds / len(rows) if rows else None,
            }

        buckets, lower = [], 0
        for fraction in self.settings.rank_buckets:
            upper = math.ceil(len(frame) * fraction)
            rows = [row for row in latest.values() if lower < row["rank"] <= upper]
            buckets.append({"rank_from": lower + 1, "rank_to": upper, **summarize(rows)})
            lower = upper
        return {
            "queue_id": queue_id,
            "total_images": len(frame),
            "reviewed_images": len(latest),
            "review_events": len(history),
            "latest": summarize(list(latest.values())),
            "history": summarize(history),
            "rank_buckets": buckets,
            "audit_events": sum(row["is_audit"] for row in history),
        }
