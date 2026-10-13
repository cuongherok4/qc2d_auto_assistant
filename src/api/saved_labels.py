"""Read persisted CVAT rectangles; never read a browser's unsaved canvas or write CVAT."""

from __future__ import annotations

import hashlib
import json
import math
import os
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from uuid import uuid4

import httpx
from fastapi import HTTPException

from src import config, contracts


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()


def atomic_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temp.write_bytes(canonical(value))
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


class SavedLabels:
    def __init__(self, settings, service, client=None):
        self.settings, self.service, self.client = settings, service, client

    def capture(self, image_id, batch=None, queue_id=None):
        detail = self.service.detail(image_id, batch, queue_id)
        target = detail["cvat"]
        if target is None:
            raise HTTPException(409, "Chưa có CVAT mapping; chạy cvat-sync trước")
        base = self.settings.cvat_url.rstrip("/") + "/"
        origin = urlsplit(base)
        if (
            origin.scheme not in {"http", "https"}
            or not origin.hostname
            or origin.username
            or origin.password
        ):
            raise HTTPException(503, "CVAT URL không hợp lệ hoặc chứa credentials")
        client, own = self.client, self.client is None
        if own:
            user, password = os.environ.get("CVAT_USER"), os.environ.get("CVAT_PASSWORD")
            if not user or not password:
                raise HTTPException(503, "Thiếu CVAT_USER/CVAT_PASSWORD ở môi trường API")
            client = httpx.Client(auth=(user, password), timeout=30, follow_redirects=False)

        def get(endpoint):
            url = urljoin(base, endpoint)
            parsed = urlsplit(url)
            if (parsed.scheme, parsed.netloc) != (origin.scheme, origin.netloc):
                raise HTTPException(503, "CVAT pagination trỏ ra ngoài origin")
            try:
                response = client.get(url)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as exc:
                raise HTTPException(503, f"CVAT HTTP {exc.response.status_code}; kiểm tra quyền") from None
            except (httpx.HTTPError, ValueError):
                raise HTTPException(503, "Không đọc được JSON từ CVAT") from None

        try:
            job = get(f"api/jobs/{target['job_id']}")
            if int(job["task_id"]) != target["task_id"] or job.get("type", "annotation") != "annotation":
                raise ValueError("Mapping không trỏ vào annotation job của task")
            start, stop = int(job["start_frame"]), int(job["stop_frame"])
            frame = target["frame"]
            meta = get(f"api/jobs/{target['job_id']}/data/meta")
            if len(meta["frames"]) != stop - start + 1 or not start <= frame <= stop:
                raise ValueError("Metadata frame không liên tục/không khớp mapping")
            image = meta["frames"][frame - start]
            name = Path(image["name"].replace("\\", "/")).stem
            if name != image_id or (image["width"], image["height"]) != (contracts.IMG_W, contracts.IMG_H):
                raise ValueError("Tên ảnh hoặc kích thước không đúng mapping/contract pixel 1280×720")
            labels, endpoint, seen = {}, f"api/labels?task_id={target['task_id']}&page_size=100", set()
            while endpoint:
                if endpoint in seen:
                    raise ValueError("CVAT label pagination bị lặp")
                seen.add(endpoint)
                page = get(endpoint)
                for label in page["results"]:
                    labels[int(label["id"])] = label
                endpoint = page.get("next")
            annotations = get(f"api/jobs/{target['job_id']}/annotations")
            if annotations.get("tracks"):
                raise ValueError("Job có tracks; adapter 2D này chỉ hỗ trợ rectangle shape theo ảnh")
            boxes = []
            for shape in annotations["shapes"]:
                if int(shape["frame"]) != frame:
                    continue
                if shape["type"] != "rectangle" or float(shape.get("rotation", 0)) != 0:
                    raise ValueError("Chỉ hỗ trợ rectangle không xoay; không tự bỏ qua nhãn khác")
                points = [float(n) for n in shape["points"]]
                if len(points) != 4 or any(not math.isfinite(n) for n in points):
                    raise ValueError("Toạ độ nhãn không hợp lệ")
                if points[2] <= points[0] or points[3] <= points[1]:
                    raise ValueError("Box đảo chiều")
                label = labels[int(shape["label_id"])]
                if label["name"] not in contracts.BDD_CLASSES:
                    raise ValueError("Class CVAT không đúng BDD contract; không tự đoán class")
                specs = {int(attr["id"]): attr for attr in label["attributes"]}
                attrs = {}
                for attr in shape["attributes"]:
                    spec = specs[int(attr["spec_id"])]
                    value = attr["value"]
                    if spec["input_type"] == "checkbox":
                        if value not in {"true", "false"}:
                            raise ValueError("Checkbox attribute cần true/false")
                        value = value == "true"
                    attrs[spec["name"]] = value
                attrs["occluded"] = bool(shape["occluded"])
                boxes.append(
                    {
                        "obj_id": str(shape["id"]),
                        "category": label["name"],
                        "box": points,
                        "attributes": attrs,
                    }
                )
            latest = get(f"api/jobs/{target['job_id']}/annotations")
            if canonical(latest) != canonical(annotations):
                raise HTTPException(409, "Nhãn CVAT đổi trong lúc đọc; Save xong rồi đọc lại")
            payload = {
                "image_id": image_id,
                "cvat": target,
                "cvat_origin": base.rstrip("/"),
                "annotation_version": annotations["version"],
                "width": image["width"],
                "height": image["height"],
                # Preserve CVAT's saved shape order. Server IDs identify objects;
                # they are not the per-image display order (or client-side IDs).
                "boxes": boxes,
            }
            digest = hashlib.sha256(canonical(payload)).hexdigest()
            path = config.ROOT / self.settings.snapshot_dir / f"{digest}.json"
            if path.exists() and path.read_bytes() != canonical(payload):
                raise ValueError("Snapshot đã đổi nội dung")
            if not path.exists():
                atomic_json(path, payload)
            return {
                "snapshot_id": digest,
                "snapshot_file": str(path),
                "payload": payload,
                "queue_id": detail["queue_id"],
                "captured_at": datetime.now(UTC).isoformat(),
            }
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise HTTPException(503, f"Nhãn CVAT không thể đọc an toàn: {exc}") from exc
        finally:
            if own:
                client.close()
