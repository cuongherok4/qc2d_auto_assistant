"""Local review API. Start: uvicorn src.api.main:app --host 127.0.0.1."""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.api.models import ModelManager
from src.api.pilot import validate_verdict
from src.api.recheck import RecheckManager
from src.api.saved_labels import SavedLabels
from src.api.schemas import ImageDetail, QueueResponse, SavedVerdict
from src.api.service import QueueService
from src.api.settings import Settings
from src.api.store import DuplicateSubmission, ReviewStore

ReviewOrder = Literal["priority", "file"]


class Verdict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)
    request_id: str = Field(default_factory=lambda: str(uuid4()), min_length=1, max_length=100)
    image_id: str = Field(min_length=1, max_length=200)
    verdict: Literal["error", "false_alarm", "skip"]
    reviewer: str = Field(min_length=1, max_length=100)
    seconds_spent: float = Field(ge=0, le=86400)
    note: str | None = Field(default=None, max_length=10000)
    obj_ids: list[str] = Field(default_factory=list, max_length=1000)
    batch_id: str | None = Field(default=None, max_length=100)
    queue_id: str | None = Field(default=None, max_length=64)
    model_version: str | None = Field(default=None, max_length=200)
    rank: int | None = Field(default=None, ge=1)
    session_id: str = Field(default="default", min_length=1, max_length=100)
    review_order: ReviewOrder = "priority"

    @field_validator("obj_ids")
    @classmethod
    def object_ids(cls, values):
        if any(not value or len(value) > 200 for value in values):
            raise ValueError("obj_ids phải là ID không rỗng, tối đa 200 ký tự")
        return list(dict.fromkeys(values))


class Rollback(BaseModel):
    model_version: str = Field(min_length=1, max_length=200)


class RecheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    request_id: str = Field(pattern=r"^[A-Za-z0-9-]{1,100}$")
    snapshot_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    queue_id: str = Field(pattern=r"^[a-f0-9]{64}$")


def create_app(
    settings: Settings | None = None, *, retrain_backend=None, recheck_backend=None, cvat_client=None
) -> FastAPI:
    settings = settings or Settings.configured()
    store = ReviewStore(settings.database)
    service = QueueService(settings, store)
    models = ModelManager(settings, store, service, retrain_backend)
    saved = SavedLabels(settings, service, cvat_client)
    rechecks = RecheckManager(settings, store, service, saved, recheck_backend)
    app = FastAPI(title="M13 Review Queue", version="0.2.0")
    app.state.settings, app.state.store, app.state.service = settings, store, service
    app.state.models = models
    app.state.rechecks = rechecks
    origins = list(dict.fromkeys([settings.cvat_url.rstrip("/"), *settings.allowed_origins]))
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
        allow_credentials=False,
    )

    @app.get("/health")
    def health():
        try:
            frame, queue_id, _ = service.snapshot()
            return {
                "status": "ok",
                "queue_id": queue_id,
                "model_version": str(frame.model_version.iloc[0]) if len(frame) else None,
                "queue_available": len(frame) > 0,
            }
        except HTTPException as exc:
            raise HTTPException(503, {"status": "degraded", "queue_error": exc.detail}) from exc

    @app.get("/queue", response_model=QueueResponse)
    def queue(
        limit: Annotated[int, Query(ge=1, le=500)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
        batch: str | None = None,
        reviewer: str | None = None,
        session_id: str | None = None,
        include_reviewed: bool = False,
        order: ReviewOrder = "priority",
    ):
        return service.queue(
            batch=batch,
            limit=limit,
            offset=offset,
            reviewer=reviewer,
            session_id=session_id,
            include_reviewed=include_reviewed,
            order=order,
        )

    @app.get("/image/{image_id}/file")
    def image_file(image_id: str):
        path = service.image_path(image_id)
        if path is None:
            raise HTTPException(404, "Chưa có nội dung ảnh trong images_dir")
        return FileResponse(path, headers={"Cache-Control": "no-cache"})

    @app.get("/image/{image_id}", response_model=ImageDetail)
    def image(image_id: str, batch: str | None = None, queue_id: str | None = None):
        return service.detail(image_id, batch, queue_id)

    @app.get("/image/{image_id}/saved")
    def saved_image(image_id: str, batch: str | None = None, queue_id: str | None = None):
        return rechecks.capture(image_id, batch, queue_id)

    @app.post("/image/{image_id}/recheck")
    def recheck_image(image_id: str, value: RecheckRequest):
        return rechecks.run(image_id, value.model_dump())

    @app.get("/rechecks/{request_id}")
    def recheck_status(request_id: str):
        return rechecks.status(request_id)

    @app.post("/verdict", response_model=SavedVerdict)
    def verdict(value: Verdict):
        payload = value.model_dump()
        previous = store.submission(value.request_id)
        if previous:
            for key in ("queue_id", "model_version", "rank"):
                if payload[key] is None:
                    payload[key] = previous[key]
            audit = previous["is_audit"]
        else:
            detail, is_audit = service.verdict_context(value.image_id, value.batch_id, value.queue_id)
            for key in ("queue_id", "model_version", "rank"):
                if payload[key] is not None and payload[key] != detail[key]:
                    raise HTTPException(409, f"{key} không khớp hàng đợi đang phục vụ")
                payload[key] = detail[key]
            audit = value.review_order == "priority" and is_audit
            validate_verdict(store, settings, payload)
        try:
            saved, duplicate = store.append(payload, is_audit=audit)
        except DuplicateSubmission as exc:
            raise HTTPException(409, str(exc)) from exc
        result = {key: saved[key] for key in ("id", "request_id", "image_id", "created_at")}
        if not duplicate:
            models.maybe_retrain()
        return {"status": "saved", "duplicate": duplicate, **result}

    @app.get("/stats")
    def stats(
        batch: str | None = None,
        reviewer: str | None = None,
        session_id: str | None = None,
        order: ReviewOrder | None = None,
        queue_id: str | None = None,
    ):
        return service.stats(
            batch=batch, reviewer=reviewer, session_id=session_id, order=order, queue_id=queue_id
        )

    @app.get("/model")
    def model():
        return models.info()

    @app.post("/retrain")
    def retrain():
        return models.retrain()

    @app.post("/model/rollback")
    def rollback(value: Rollback):
        return models.rollback(value.model_version)

    return app


app = create_app()
