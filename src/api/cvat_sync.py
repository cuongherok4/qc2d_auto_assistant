"""Read the local CVAT API and atomically map filenames to task/job/task-frame."""

from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from uuid import uuid4

import httpx
import pandas as pd

MAP_COLUMNS = ["image_id", "task_id", "job_id", "frame"]


class CvatSyncError(ValueError):
    pass


def sync(
    cvat_url: str,
    out_parquet: Path,
    *,
    task_ids: list[int] | None = None,
    image_ids: list[str] | None = None,
    client: httpx.Client | None = None,
) -> int:
    """Fail on ambiguous filenames; missing requested images go in a local report.

    Frame numbering follows CVAT SDK's task-file-to-job recipe: job.start_frame +
    offset within job.get_frames_info(). Ground-truth jobs are not review targets.
    """
    parsed = urlsplit(cvat_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise CvatSyncError("CVAT URL cần http(s), không chứa credentials")
    own_client = client is None
    if own_client:
        user, password = os.environ.get("CVAT_USER"), os.environ.get("CVAT_PASSWORD")
        if not user or not password:
            raise CvatSyncError("Thiếu CVAT_USER/CVAT_PASSWORD trong môi trường")
        client = httpx.Client(auth=(user, password), timeout=30, follow_redirects=False)
    origin = (parsed.scheme, parsed.netloc)
    base = cvat_url.rstrip("/") + "/"

    def get(url):
        target = urlsplit(url)
        if (target.scheme, target.netloc) != origin:
            raise CvatSyncError("CVAT pagination trỏ ra ngoài origin đã cấu hình")
        try:
            response = client.get(url)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            message = f"CVAT trả HTTP {exc.response.status_code}; kiểm tra tài khoản/quyền"
            raise CvatSyncError(message) from None
        except (httpx.HTTPError, ValueError):
            raise CvatSyncError("Không đọc được CVAT; kiểm tra kết nối và JSON API") from None

    def pages(endpoint):
        url, seen = urljoin(base, endpoint), set()
        while url:
            if url in seen:
                raise CvatSyncError("CVAT pagination bị lặp")
            seen.add(url)
            payload = get(url)
            if isinstance(payload, list):
                yield from payload
                break
            if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
                raise CvatSyncError("CVAT list API thiếu results")
            yield from payload["results"]
            url = urljoin(url, payload["next"]) if payload.get("next") else None

    expected = set(image_ids) if image_ids is not None else None
    rows = {}
    try:
        tasks = task_ids if task_ids is not None else [int(t["id"]) for t in pages("api/tasks?page_size=100")]
        for task_id in tasks:
            for job in pages(f"api/jobs?task_id={int(task_id)}&page_size=100"):
                if job.get("type", "annotation") != "annotation":
                    continue
                if int(job.get("task_id", task_id)) != int(task_id):
                    raise CvatSyncError("CVAT trả job thuộc task khác")
                meta = get(urljoin(base, f"api/jobs/{int(job['id'])}/data/meta"))
                frames = meta.get("frames")
                if not isinstance(frames, list):
                    raise CvatSyncError("CVAT job metadata thiếu frames")
                start = int(job["start_frame"])
                stop = int(job["stop_frame"])
                if len(frames) != stop - start + 1:
                    raise CvatSyncError("Job frames không liên tục; không thể đoán frame từ metadata")
                for offset, frame in enumerate(frames):
                    image_id = Path(frame["name"].replace("\\", "/")).stem
                    if expected is not None and image_id not in expected:
                        continue
                    target = {
                        "image_id": image_id,
                        "task_id": int(task_id),
                        "job_id": int(job["id"]),
                        "frame": start + offset,
                    }
                    if image_id in rows:
                        raise CvatSyncError(f"Tên ảnh mơ hồ: {image_id}; chọn --task-id hoặc sửa tên/overlap")
                    rows[image_id] = target
        table = pd.DataFrame(list(rows.values()), columns=MAP_COLUMNS).sort_values("image_id")
        missing = sorted(expected - set(rows)) if expected is not None else []
        out_parquet.parent.mkdir(parents=True, exist_ok=True)
        temporary = out_parquet.with_name(f".{out_parquet.name}.{uuid4().hex}.tmp")
        try:
            table.to_parquet(temporary, index=False)
            temporary.replace(out_parquet)
        finally:
            temporary.unlink(missing_ok=True)
        report = {"matched": len(table), "missing": missing, "tasks": tasks, "cvat_url": cvat_url}
        out_parquet.with_suffix(".report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return len(table)
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, CvatSyncError):
            raise
        raise CvatSyncError("CVAT metadata không hợp lệ; mapping cũ được giữ nguyên") from exc
    finally:
        if own_client:
            client.close()
