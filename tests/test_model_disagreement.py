"""4 tín hiệu bất đồng với detector: kích hoạt, không kích hoạt, ảnh không có box, class COCO không có."""

import pandas as pd

from src import contracts
from src.data import bdd100k
from src.features import model_disagreement as md


def _tables(boxes_by_image):
    frames = [{"name": f"{img}.jpg", "attributes": {},
               "labels": [{"id": str(i), "category": c, "attributes": {},
                           "box2d": dict(zip(("x1", "y1", "x2", "y2"), b, strict=True))}
                          for i, (c, b) in enumerate(boxes)]}
              for img, boxes in boxes_by_image.items()]
    return bdd100k.to_tables(frames)


def _preds(rows):
    return pd.DataFrame([(img, *b, c, conf) for img, c, b, conf in rows], columns=contracts.PRED_COLS)


CAR = (100, 100, 300, 250)


def test_missing_label_and_label_unsupported():
    objects, images = _tables({"miss": [], "fake": [("car", CAR)], "ok": [("car", CAR)], "empty": []})
    preds = _preds([("miss", "pedestrian", (500, 200, 540, 320), 0.9),
                    ("ok", "car", (102, 100, 300, 252), 0.9)])
    miss = md.model_missing_label(objects, images, preds)
    assert set(miss) == set(images.image_id)
    assert miss["miss"].value > 0 and "pedestrian cao 120px" in miss["miss"].reason
    assert miss["ok"].value == 0 and miss["empty"].value == 0 and miss["fake"].value == 0
    fake = md.label_unsupported(objects, images, preds)
    assert fake["fake"].value > 0 and "car #0" in fake["fake"].reason
    assert fake["ok"].value == 0 and fake["empty"].value == 0


def test_class_conflict_and_coco_gaps():
    objects, images = _tables({
        "wrong": [("truck", CAR)],
        "unsure": [("truck", CAR)],
        "rider": [("rider", (100, 100, 140, 200))],
        "sign": [("traffic sign", (100, 100, 140, 140))],
        "empty": [],
    })
    preds = _preds([
        ("wrong", "car", CAR, 0.9),
        ("unsure", "car", CAR, 0.9), ("unsure", "truck", (101, 100, 300, 250), 0.6),
        ("rider", "pedestrian", (100, 100, 140, 200), 0.9),
        ("sign", "traffic light", (100, 100, 140, 140), 0.9),
    ])
    out = md.model_class_conflict(objects, images, preds)
    assert out["wrong"].value > 0 and "model thấy car (conf 0.90" in out["wrong"].reason
    assert all(out[k].value == 0 for k in ("unsure", "rider", "sign", "empty"))
    # Dự đoán đè lên rider / traffic sign không bị báo thiếu box, nhãn của chúng không bị báo box giả.
    assert md.model_missing_label(objects, images, preds)["rider"].value == 0
    assert md.label_unsupported(objects, images, preds)["sign"].value == 0


def test_loose_box_and_options():
    objects, images = _tables({"shift": [("car", CAR)], "tight": [("car", CAR)], "empty": []})
    preds = _preds([("shift", "car", (150, 100, 350, 250), 0.9), ("tight", "car", CAR, 0.9)])
    out = md.model_loose_box(objects, images, preds)
    assert out["shift"].value > 0 and "IoU 0.60 < 0.70" in out["shift"].reason
    assert out["tight"].value == 0 and out["empty"].value == 0
    assert md.model_loose_box(objects, images, preds, {"loose_iou": 0.55})["shift"].value == 0


def test_spec_drops_predictions_below_min_height():
    objects, images = _tables({"small": []})
    preds = _preds([("small", "pedestrian", (500, 200, 520, 240), 0.9)])  # cao 40px
    assert md.model_missing_label(objects, images, preds)["small"].value > 0
    spec = {"min_height_px": {"default": 50}, "merge": {}}
    assert md.model_missing_label(objects, images, preds, {"spec": spec})["small"].value == 0


def test_loose_box_catches_shift_below_min_iou():
    objects, images = _tables({"shift35": [("car", CAR)]})
    preds = _preds([("shift35", "car", (170, 100, 370, 250), 0.9)])  # dịch 35% bề rộng: IoU 0.48 < min_iou
    out = md.model_loose_box(objects, images, preds)["shift35"]
    assert out.value > 0 and "IoU 0.48" in out.reason
    # IoU dưới min_iou không được coi là "khớp nhưng khác class"
    preds.loc[0, "category"] = "truck"
    assert md.model_class_conflict(objects, images, preds)["shift35"].value == 0


def test_ego_hood_prediction_is_not_missing_label():
    objects, images = _tables({"hood": [("car", CAR)]})
    preds = _preds([("hood", "car", CAR, 0.9), ("hood", "car", (0, 520, 1280, 720), 0.8)])
    assert md.model_missing_label(objects, images, preds)["hood"].value == 0
    assert md.model_missing_label(objects, images, preds, {"ego_min_w": 2000})["hood"].value > 0
