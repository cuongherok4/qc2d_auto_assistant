"""Documented review response schema; audit assignment is intentionally absent."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Evidence(BaseModel):
    obj_id: str | None = None
    box: list[float] = Field(min_length=4, max_length=4)
    note: str = ""
    signal: str | None = None
    severity: Literal["error", "review"] = "review"  # màu box: đỏ / vàng


class CvatTarget(BaseModel):
    task_id: int = Field(ge=1)
    job_id: int = Field(ge=1)
    frame: int = Field(ge=0)


class QueueItem(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    image_id: str
    risk_score: float = Field(ge=0, le=100)
    rank: int = Field(ge=1)
    top_reasons: str
    model_version: str
    queue_id: str
    batch_id: str | None
    reasons: list[str] = Field(max_length=3)
    evidence: list[Evidence]
    cvat_url: str | None
    cvat: CvatTarget | None
    image_url: str
    image_available: bool


class QueueResponse(BaseModel):
    items: list[QueueItem]
    total: int
    remaining: int
    reviewed: int
    offset: int
    limit: int
    queue_id: str
    model_version: str | None
    batch_id: str | None
    warnings: list[str]


class Prediction(BaseModel):
    image_id: str
    x1: float
    y1: float
    x2: float
    y2: float
    category: str
    conf: float = Field(ge=0, le=1)


class ImageDetail(QueueItem):
    predictions: list[Prediction]
    warnings: list[str]


class SavedVerdict(BaseModel):
    status: Literal["saved"]
    duplicate: bool
    id: int
    request_id: str
    image_id: str
    created_at: str
