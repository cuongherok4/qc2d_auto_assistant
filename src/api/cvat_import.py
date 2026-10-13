"""Upload only a queue's images and 2D BDD labels into a NEW local CVAT task."""

from __future__ import annotations

import os
import time
from contextlib import ExitStack
from pathlib import Path
from urllib.parse import quote, urlsplit

import httpx
import pandas as pd

from src import contracts
from src.data import bdd100k


def import_batch(
    cvat_url: str,
    queue_file: Path,
    images_dir: Path,
    labels_file: Path,
    task_name: str,
    *,
    client: httpx.Client | None = None,
    timeout: float = 180,
) -> dict:
    url = urlsplit(cvat_url)
    if url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password:
        raise ValueError("CVAT URL không hợp lệ hoặc chứa credentials")
    queue = pd.read_csv(queue_file, dtype={"image_id": str})
    if errors := contracts.check_queue(queue):
        raise ValueError("; ".join(errors))
    expected = set(queue.image_id)
    if not expected:
        raise ValueError("Không import hàng đợi rỗng")
    root = images_dir.resolve()
    paths = []
    for image_id in sorted(expected):
        candidates = [root / f"{image_id}{suffix}" for suffix in (".jpg", ".png", ".jpeg")]
        found = [p for p in candidates if p.is_file() and p.resolve().is_relative_to(root)]
        if len(found) != 1:
            raise ValueError(f"Ảnh thiếu hoặc mơ hồ: {image_id}")
        paths.append(found[0])
    frames = [frame for frame in bdd100k.read_frames(labels_file) if Path(frame["name"]).stem in expected]
    if {Path(frame["name"]).stem for frame in frames} != expected:
        raise ValueError("BDD labels thiếu ảnh có trong queue")
    objects, _ = bdd100k.to_tables(frames)
    if set(objects.category) - set(contracts.BDD_CLASSES):
        raise ValueError("Class không đúng BDD contract")
    own = client is None
    if own:
        user, password = os.environ.get("CVAT_USER"), os.environ.get("CVAT_PASSWORD")
        if not user or not password:
            raise ValueError("Thiếu CVAT_USER/CVAT_PASSWORD")
        client = httpx.Client(auth=(user, password), timeout=30, follow_redirects=False)
    base = cvat_url.rstrip("/")
    task_id = None

    def call(method, endpoint, **kwargs):
        try:
            response = client.request(method, base + endpoint, **kwargs)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            raise ValueError(
                f"CVAT HTTP {exc.response.status_code}; task mới {task_id}, kiểm tra quyền/schema"
            ) from None
        except (httpx.HTTPError, ValueError):
            raise ValueError(f"Không đọc được CVAT; task mới {task_id} có thể chưa import xong") from None

    try:
        existing = call("GET", "/api/tasks", params={"name": task_name})
        if existing.get("count", 0):
            raise ValueError("Task cùng tên đã tồn tại; không ghi đè nhãn, chọn tên mới hoặc dùng task đã có")
        attrs = [
            {
                "name": name,
                "input_type": "checkbox",
                "mutable": True,
                "default_value": "false",
                "values": ["false"],
            }
            for name in ("occluded", "truncated")
        ]
        task = call(
            "POST",
            "/api/tasks",
            json={
                "name": task_name,
                "segment_size": 0,
                "labels": [
                    {"name": name, "type": "rectangle", "attributes": attrs} for name in contracts.BDD_CLASSES
                ],
            },
        )
        task_id = int(task["id"])
        with ExitStack() as stack:
            files = [
                (f"client_files[{i}]", (path.name, stack.enter_context(path.open("rb"))))
                for i, path in enumerate(paths)
            ]
            request = call(
                "POST",
                f"/api/tasks/{task_id}/data",
                files=files,
                data={"image_quality": "90", "sorting_method": "lexicographical"},
                timeout=timeout,
            )
        request_id = quote(request["rq_id"], safe="")
        deadline = time.monotonic() + timeout
        while True:
            status = call("GET", f"/api/requests/{request_id}")
            if status["status"] == "finished":
                break
            if status["status"] == "failed":
                raise ValueError(f"CVAT import failed; kiểm tra task #{task_id} trên UI")
            if time.monotonic() >= deadline:
                raise ValueError(f"Hết thời gian chờ CVAT import task #{task_id}; không tự xoá task")
            time.sleep(1)
        meta = call("GET", f"/api/tasks/{task_id}/data/meta")
        names = [Path(frame["name"]).stem for frame in meta["frames"]]
        if set(names) != expected or len(names) != len(expected):
            raise ValueError(f"Tên/frame CVAT không khớp; chưa ghi nhãn vào task #{task_id}")
        frame_index = {name: i for i, name in enumerate(names)}
        labels = call("GET", "/api/labels", params={"task_id": task_id, "page_size": 100})["results"]
        labels_by_name = {label["name"]: label for label in labels}
        shapes = []
        for row in objects.to_dict("records"):
            label = labels_by_name[row["category"]]
            shapes.append(
                {
                    "type": "rectangle",
                    "frame": frame_index[row["image_id"]],
                    "label_id": label["id"],
                    "occluded": row["occluded"],
                    "z_order": 0,
                    "points": [row[k] for k in ("x1", "y1", "x2", "y2")],
                    "rotation": 0,
                    "attributes": [
                        {"spec_id": attr["id"], "value": str(row[attr["name"]]).lower()}
                        for attr in label["attributes"]
                    ],
                }
            )
        call(
            "PUT",
            f"/api/tasks/{task_id}/annotations",
            json={"version": 0, "tags": [], "shapes": shapes, "tracks": []},
        )
        readback = call("GET", f"/api/tasks/{task_id}/annotations")

        def signature(shape):
            return (
                shape["frame"],
                shape["label_id"],
                shape["type"],
                tuple(round(float(n), 4) for n in shape["points"]),
                bool(shape["occluded"]),
                tuple(sorted((a["spec_id"], a["value"]) for a in shape["attributes"])),
            )

        if sorted(map(signature, readback["shapes"])) != sorted(map(signature, shapes)):
            raise ValueError(f"Nhãn đọc lại không khớp task #{task_id}; chưa xác nhận import thành công")
        return {
            "task_id": task_id,
            "images": len(paths),
            "boxes": len(shapes),
            "cvat_url": f"{base}/tasks/{task_id}",
            "name": task_name,
        }
    finally:
        if own:
            client.close()
