"""Đọc nhãn BDD100K detection 2D (det_20) thành 2 bảng:

- objects: mỗi dòng một box  (image_id, obj_id, category, x1..y2, w, h, area, occluded, truncated,
           weather, timeofday, scene, has_occluded, has_truncated)
- images:  mỗi dòng một ảnh  (image_id, weather, timeofday, scene, n_boxes), GIỮ cả ảnh không có box.

Chi tiết định dạng và các chỗ dễ sai: skill `bdd100k-data`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src import config

OBJ_COLS = [
    "image_id", "obj_id", "category", "x1", "y1", "x2", "y2", "w", "h", "area",
    "occluded", "truncated", "weather", "timeofday", "scene", "has_occluded", "has_truncated",
]
IMG_COLS = ["image_id", "weather", "timeofday", "scene", "n_boxes"]


def read_frames(json_path: Path | str | None = None) -> list[dict]:
    with open(json_path or config.path("labels_json"), encoding="utf-8") as f:
        return json.load(f)


def to_tables(frames: list[dict]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """frames (JSON BDD) -> (objects, images). Tên class cũ được map về 10 class chuẩn ngay tại đây."""
    rename = config.load("class_map")["rename"]
    obj_rows, img_rows = [], []
    for fr in frames:
        image_id = fr["name"].removesuffix(".jpg")
        attrs = fr.get("attributes") or {}
        ctx = {k: attrs.get(k, "undefined") for k in ("weather", "timeofday", "scene")}
        n = 0
        for idx, lb in enumerate(fr.get("labels") or []):
            box = lb.get("box2d")
            if not box:  # poly2d (lane, drivable area) không phải detection
                continue
            la = lb.get("attributes") or {}
            obj_rows.append({
                "image_id": image_id,
                "obj_id": str(lb.get("id", idx)),
                "category": rename.get(lb["category"], lb["category"]),
                **{k: float(box[k]) for k in ("x1", "y1", "x2", "y2")},
                "occluded": bool(la.get("occluded", False)),
                "truncated": bool(la.get("truncated", False)),
                # phân biệt "không có thuộc tính" với "có, giá trị false" (luật R3)
                "has_occluded": "occluded" in la,
                "has_truncated": "truncated" in la,
                **ctx,
            })
            n += 1
        img_rows.append({"image_id": image_id, **ctx, "n_boxes": n})
    objects = pd.DataFrame(obj_rows, columns=[c for c in OBJ_COLS if c not in ("w", "h", "area")])
    objects["w"] = objects["x2"] - objects["x1"]
    objects["h"] = objects["y2"] - objects["y1"]
    objects["area"] = objects["w"] * objects["h"]
    return objects[OBJ_COLS], pd.DataFrame(img_rows, columns=IMG_COLS)


def load(json_path: Path | str | None = None, use_cache: bool = True) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Đọc nhãn (mặc định configs/paths.yaml: labels_json), cache parquet trong data/cache/."""
    src = Path(json_path or config.path("labels_json"))
    cache_dir = config.path("cache_dir")
    obj_p, img_p = cache_dir / f"{src.stem}_objects.parquet", cache_dir / f"{src.stem}_images.parquet"
    if use_cache and obj_p.exists() and obj_p.stat().st_mtime >= src.stat().st_mtime:
        objects = pd.read_parquet(obj_p)
        if set(OBJ_COLS) <= set(objects.columns):  # cache sinh trước khi thêm cột thì đọc lại từ JSON
            return objects, pd.read_parquet(img_p)
    objects, images = to_tables(read_frames(src))
    if use_cache:
        cache_dir.mkdir(parents=True, exist_ok=True)
        objects.to_parquet(obj_p, index=False)
        images.to_parquet(img_p, index=False)
    return objects, images
