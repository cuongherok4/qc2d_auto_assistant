"""Bước 5–6 · API phục vụ hàng đợi review và lưu verdict. Phụ trách: Tú Anh.
Hướng dẫn: skill `review-queue`. Chạy: uvicorn src.api.main:app --reload

/health và /queue đã chạy được (đọc ranked_queue mới nhất trong reports/). Còn lại là TODO.
"""

from __future__ import annotations

from typing import Literal

import pandas as pd
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from src import config

app = FastAPI(title="M13 Review Queue")


def latest_queue() -> pd.DataFrame | None:
    files = sorted(config.path("reports_dir").glob("ranked_queue_*.csv"), key=lambda p: p.stat().st_mtime)
    return pd.read_csv(files[-1]) if files else None


@app.get("/health")
def health():
    q = latest_queue()
    return {"status": "ok", "model_version": None if q is None else str(q["model_version"].iloc[0])}


@app.get("/queue")
def queue(limit: int = 50, offset: int = 0):
    q = latest_queue()
    if q is None:
        raise HTTPException(404, "Chưa có reports/ranked_queue_*.csv, chạy: python -m src.cli rank")
    q = q.sort_values("rank").iloc[offset: offset + limit].fillna("")
    return q.to_dict(orient="records")


class Verdict(BaseModel):
    image_id: str
    verdict: Literal["error", "false_alarm", "skip"]
    reviewer: str
    seconds_spent: float
    note: str | None = None


@app.post("/verdict")
def verdict(v: Verdict):
    raise HTTPException(501, "TODO(Tú Anh): lưu verdict vào SQLite (chỉ thêm, không sửa)")
