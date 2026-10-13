"""Bước 2 · Tiêm lỗi có đáp án. Phụ trách: Cường. Hướng dẫn: skill `error-injection`.

Đầu vào : det_val.json gốc + configs/injection.yaml
Đầu ra  : data/injected/det_val_injected.json   (cùng định dạng BDD, các bước sau dùng như dữ liệu thật)
          data/injected/injected_errors.json     ({meta, image_order, splits, errors})
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import random

from src import config
from src.contracts import IMG_H, IMG_W
from src.features.geometry import iou_matrix


def _box(label):
    b = label["box2d"]
    return [float(b[k]) for k in ("x1", "y1", "x2", "y2")]


def _valid(box, minimum):
    x1, y1, x2, y2 = box
    return (all(math.isfinite(x) for x in box) and 0 <= x1 < x2 <= IMG_W
            and 0 <= y1 < y2 <= IMG_H and x2-x1 >= minimum and y2-y1 >= minimum)


def _transform(before, kind, rng, cfg):
    x1, y1, x2, y2 = before
    w, h = x2-x1, y2-y1
    lo, hi = cfg["shift_iou_range"]
    for _ in range(cfg.get("max_attempts", 100)):
        if kind == "shift":
            dx, dy = rng.uniform(-.5, .5)*w, rng.uniform(-.5, .5)*h
            box = [x1+dx, y1+dy, x2+dx, y2+dy]
        else:
            scale = rng.uniform(.6, 1.6)
            cx, cy = (x1+x2)/2, (y1+y2)/2
            box = [cx-w*scale/2, cy-h*scale/2, cx+w*scale/2, cy+h*scale/2]
        box = [max(0, min(v, limit)) for v, limit in zip(box, [IMG_W, IMG_H]*2, strict=True)]
        if _valid(box, cfg["min_box_side_px"]) and lo <= iou_matrix([before], [box])[0, 0] < hi:
            return box
    return None


def _spurious(category, sizes, labels, rng, cfg):
    for _ in range(cfg.get("max_attempts", 100)):
        w, h = rng.choice(sizes[category])
        x, y = rng.uniform(0, IMG_W-w), rng.uniform(0, IMG_H-h)
        box = [x, y, x+w, y+h]
        others = [_box(lb) for lb in labels if lb.get("box2d")]
        if not others or iou_matrix([box], others).max() < cfg.get("spurious_max_iou", .1):
            return box
    return None


def _validate(cfg):
    if not 0 <= cfg["rate"] <= 1:
        raise ValueError("rate phải trong [0,1]")
    low, high = cfg["errors_per_image"]
    if not isinstance(low, int) or not isinstance(high, int) or not 1 <= low <= high:
        raise ValueError("errors_per_image phải là hai số nguyên 1 <= min <= max")
    splits = cfg["splits"]
    if set(splits) != {"train", "val", "test"} or any(v < 0 for v in splits.values()):
        raise ValueError("splits cần train/val/test không âm")
    if not math.isclose(sum(splits.values()), 1):
        raise ValueError("Tổng tỉ lệ split phải bằng 1")
    allowed = {"missing", "wrong_class", "spurious", "shift", "resize"}
    if not cfg["types"] or set(cfg["types"]) - allowed or any(v <= 0 for v in cfg["types"].values()):
        raise ValueError("types phải là các loại lỗi hỗ trợ với trọng số dương")
    if set(cfg["test_only"]) - set(cfg["types"]):
        raise ValueError("test_only chứa loại lỗi không được cấu hình")
    if not 0 < cfg["shift_iou_range"][0] < cfg["shift_iou_range"][1] <= 1:
        raise ValueError("shift_iou_range không hợp lệ")
    if cfg["min_box_side_px"] <= 0 or cfg.get("max_attempts", 100) < 1:
        raise ValueError("Kích thước tối thiểu và số lần thử phải dương")
    if cfg.get("sampling", "realistic") not in {"realistic", "uniform"}:
        raise ValueError("sampling phải là realistic hoặc uniform")


def inject(frames: list[dict], cfg: dict) -> tuple[list[dict], dict]:
    """Trả về (frames_đã_tiêm, đáp_án). Cùng seed phải ra cùng đáp án."""
    _validate(cfg)
    result = copy.deepcopy(frames)
    order = [fr["name"].removesuffix(".jpg") for fr in frames]
    if len(set(order)) != len(order):
        raise ValueError("image_id bị trùng")
    rng = random.Random(cfg["seed"])
    shuffled = sorted(order)
    rng.shuffle(shuffled)
    n_train = int(len(order)*cfg["splits"]["train"])
    n_val = int(len(order)*cfg["splits"]["val"])
    splits = {img: "train" if i < n_train else "val" if i < n_train+n_val else "test"
              for i, img in enumerate(shuffled)}
    rename = config.load("class_map")["rename"]
    sizes, candidates = {}, {}
    for image_id, fr in zip(order, result, strict=True):
        valid, ids = [], set()
        for idx, lb in enumerate(fr.get("labels") or []):
            if not lb.get("box2d"):
                continue
            obj_id = str(lb.get("id", idx))
            if obj_id in ids:
                raise ValueError(f"{image_id}: obj_id trùng {obj_id}")
            ids.add(obj_id)
            lb.setdefault("id", obj_id)
            if not _valid(_box(lb), cfg["min_box_side_px"]):
                continue
            valid.append(lb)
            cat = rename.get(lb["category"], lb["category"])
            x1, y1, x2, y2 = _box(lb)
            sizes.setdefault(cat, []).append((x2-x1, y2-y1))
        candidates[image_id] = valid
    errors, skipped = [], []
    selected = set()
    for split in ("train", "val", "test"):
        eligible = sorted(i for i in order if splits[i] == split and candidates[i])
        selected.update(rng.sample(eligible, math.floor(len(eligible)*cfg["rate"]+.5)))
    for image_id, fr in zip(order, result, strict=True):
        if image_id not in selected:
            continue
        split = splits[image_id]
        pool = list(candidates[image_id])
        types = [t for t in cfg["types"] if split == "test" or t not in cfg["test_only"]]
        if not types:
            raise ValueError(f"Không có loại lỗi cho split {split}")
        count = min(len(pool), rng.randint(*cfg["errors_per_image"]))
        for _ in range(count):
            kind = rng.choice(types)
            weights = []
            for lb in pool:
                b = _box(lb)
                weight = 1.
                if kind == "missing" and cfg.get("sampling", "realistic") == "realistic":
                    bias = cfg.get("missing_bias", {})
                    if b[3]-b[1] < bias.get("small_height_px", 30):
                        weight *= bias.get("small_weight", 2.)
                    if (lb.get("attributes") or {}).get("occluded"):
                        weight *= bias.get("occluded_weight", 2.)
                weights.append(weight)
            lb = rng.choices(pool, weights=weights, k=1)[0]
            pool.remove(lb)
            before = _box(lb)
            category = rename.get(lb["category"], lb["category"])
            event = {"image_id": image_id, "split": split, "type": kind,
                     "obj_id": str(lb["id"]), "category": category, "box_before": before,
                     "box_after": before.copy()}
            if kind == "missing":
                fr["labels"].remove(lb)
                event["box_after"] = None
            elif kind == "wrong_class":
                alternatives = sorted({b if a == category else a for a, b in cfg["confusable_pairs"]
                                       if category in (a, b) and a != b})
                if not alternatives:
                    skipped.append({"image_id": image_id, "obj_id": str(lb["id"]), "type": kind})
                    continue
                lb["category"] = rng.choice(alternatives)
                event["category_after"] = lb["category"]
            elif kind in {"shift", "resize"}:
                after = _transform(before, kind, rng, cfg)
                if after is None:
                    skipped.append({"image_id": image_id, "obj_id": str(lb["id"]), "type": kind})
                    continue
                lb["box2d"] = dict(zip(("x1", "y1", "x2", "y2"), after, strict=True))
                event["box_after"] = after
            else:
                after = _spurious(category, sizes, fr["labels"], rng, cfg)
                if after is None:
                    skipped.append({"image_id": image_id, "obj_id": str(lb["id"]), "type": kind})
                    continue
                used_ids = {str(obj.get("id")) for obj in fr["labels"]}
                fake_id = f"injected-{len(errors)}"
                while fake_id in used_ids:
                    fake_id += "-new"
                fr["labels"].append({"id": fake_id, "category": category,
                                     "attributes": {"occluded": False, "truncated": False},
                                     "box2d": dict(zip(("x1", "y1", "x2", "y2"), after, strict=True))})
                event.update(obj_id=fake_id, box_before=None, box_after=after)
            errors.append(event)
    answer = {"meta": {"seed": cfg["seed"], "rate": cfg["rate"], "weights": cfg["types"],
                       "config": copy.deepcopy(cfg),
                       "config_hash": hashlib.sha256(json.dumps(cfg, sort_keys=True).encode()).hexdigest(),
                       "selected_images": len(selected),
                       "corrupted_images": len({e['image_id'] for e in errors}),
                       "skipped": skipped, "purpose": "synthetic_errors_not_real_qc"},
              "image_order": order, "splits": splits, "errors": errors}
    return result, answer
