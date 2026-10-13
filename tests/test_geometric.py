"""3 tín hiệu hình học: kích hoạt, không kích hoạt, ảnh không có box."""

from src.data import bdd100k
from src.features import geometric


def _tables(boxes_by_image):
    frames = [{"name": f"{img}.jpg", "attributes": {},
               "labels": [{"id": str(i), "category": c, "attributes": {},
                           "box2d": dict(zip(("x1", "y1", "x2", "y2"), b, strict=True))}
                          for i, (c, b) in enumerate(boxes)]}
              for img, boxes in boxes_by_image.items()]
    return bdd100k.to_tables(frames)


def test_size_outlier_flags_box_far_from_class_size():
    data = {f"normal-{k}": [("car", (100, 300, 100 + 60 + k % 7, 340 + k % 5))] for k in range(40)}
    data["giant"] = [("car", (0, 0, 1200, 700))]
    data["empty"] = []
    objects, images = _tables(data)
    out = geometric.size_outlier(objects, images)
    assert set(out) == set(images.image_id)
    assert out["giant"].value > 0 and "lớn hơn" in out["giant"].reason
    assert any(ch.isdigit() for ch in out["giant"].reason)
    assert out["giant"].evidence[0]["obj_id"] == "0"
    assert out["normal-3"].value == 0 and out["empty"].value == 0


def test_size_outlier_skips_classes_with_few_boxes():
    objects, images = _tables({"a": [("train", (0, 0, 1200, 700))], "b": [("train", (10, 10, 20, 20))]})
    assert all(r.value == 0 for r in geometric.size_outlier(objects, images).values())


def test_dup_same_class():
    objects, images = _tables({
        "dup": [("car", (100, 100, 200, 180)), ("car", (102, 101, 201, 181))],
        "apart": [("car", (100, 100, 200, 180)), ("car", (400, 100, 500, 180))],
        "cross": [("car", (100, 100, 200, 180)), ("truck", (102, 101, 201, 181))],
        "empty": [],
    })
    out = geometric.dup_same_class(objects, images)
    assert out["dup"].value > 0.9 and "IoU 0.9" in out["dup"].reason
    assert {e["obj_id"] for e in out["dup"].evidence} == {"0", "1"}
    assert out["apart"].value == 0 and out["cross"].value == 0 and out["empty"].value == 0


def test_overlap_cross_class_skips_allowed_pairs():
    objects, images = _tables({
        "conflict": [("car", (100, 100, 200, 180)), ("truck", (101, 100, 200, 181))],
        "rider": [("rider", (100, 100, 140, 200)), ("bicycle", (100, 102, 140, 200))],
        "loose": [("car", (100, 100, 200, 180)), ("truck", (150, 100, 250, 180))],
        "empty": [],
    })
    out = geometric.overlap_cross_class(objects, images)
    assert out["conflict"].value > 0.5 and "sai class" in out["conflict"].reason
    assert out["rider"].value == 0 and out["loose"].value == 0 and out["empty"].value == 0


def test_options_override_defaults():
    objects, images = _tables({"pair": [("car", (100, 100, 200, 180)), ("car", (150, 100, 250, 180))]})
    assert geometric.dup_same_class(objects, images)["pair"].value == 0  # IoU 0.33 < 0.5
    loose = geometric.dup_same_class(objects, images, {"dup_same_class": {"iou_thr": 0.3}})
    assert loose["pair"].value > 0
