"""4 tín hiệu dễ: mỗi tín hiệu có ca kích hoạt, ca không kích hoạt và ca ảnh không có box."""
from pathlib import Path

import pytest

from src.data import bdd100k
from src.features import simple_signals as ss

FIXTURE = Path(__file__).parent / "fixtures" / "det_mini.json"


def make(boxes: dict[str, list[tuple]], empty: tuple[str, ...] = ("img-empty",)):
    """boxes: {image_id: [(category, x1, y1, x2, y2, truncated), ...]} -> (objects, images)."""
    frames = [{"name": f"{img}.jpg", "attributes": {"weather": "clear", "timeofday": "daytime"},
               "labels": [{"id": str(i), "category": c, "attributes": {"truncated": t},
                           "box2d": {"x1": x1, "y1": y1, "x2": x2, "y2": y2}}
                          for i, (c, x1, y1, x2, y2, t) in enumerate(bs, 1)]}
              for img, bs in boxes.items()]
    frames += [{"name": f"{img}.jpg", "labels": None} for img in empty]
    return bdd100k.to_tables(frames)


def car(x1=100.0, y1=300.0, h=100.0, truncated=False):
    return ("car", x1, y1, x1 + 80, y1 + h, truncated)


def assert_all_images(out, images):
    assert set(out) == set(images["image_id"])
    for r in out.values():
        if r.value > 0:
            assert any(ch.isdigit() for ch in r.reason)
        else:
            assert r.reason == ""


@pytest.mark.parametrize("fn", list(ss.SIGNALS.values()))
def test_every_signal_covers_all_images(fn):
    objects, images = bdd100k.to_tables(bdd100k.read_frames(FIXTURE))
    out = fn(objects, images)
    assert_all_images(out, images)
    assert out["img-empty-3"].value == 0


@pytest.mark.parametrize("fn", list(ss.SIGNALS.values()))
def test_every_signal_handles_no_objects(fn):
    objects, images = make({}, empty=("a", "b"))
    out = fn(objects, images)
    assert {k: v.value for k, v in out.items()} == {"a": 0.0, "b": 0.0}


def test_crowded():
    boxes = {f"img-{i}": [car(x1=10.0 * j) for j in range(2)] for i in range(19)}
    boxes["img-busy"] = [car(x1=10.0 * j) for j in range(30)]
    objects, images = make(boxes)
    out = ss.crowded(objects, images)
    assert_all_images(out, images)
    assert out["img-busy"].value == 1.0
    assert "30 box" in out["img-busy"].reason
    assert out["img-0"].value == 0  # 19 ảnh cùng 2 box: hoà hạng, không bị coi là đông
    assert out["img-empty"].value == 0


def test_many_tiny():
    tiny = [car(x1=50.0 * j, h=8.0 + j) for j in range(5)]
    objects, images = make({"img-tiny": tiny, "img-few": tiny[:2], "img-big": [car()]})
    out = ss.many_tiny(objects, images)
    assert_all_images(out, images)
    assert out["img-tiny"].value == pytest.approx(0.5)
    assert "5 box cao dưới 20px" in out["img-tiny"].reason
    assert "cao 8px" in out["img-tiny"].reason
    assert len(out["img-tiny"].evidence) == 5
    assert out["img-few"].value == 0  # dưới min_count
    assert out["img-big"].value == 0
    assert ss.many_tiny(objects, images, {"many_tiny": {"min_count": 2}})["img-few"].value > 0


def test_rare_class():
    common = {f"img-{i}": [car(x1=10.0 * j) for j in range(10)] for i in range(20)}
    common["img-train"] = [("train", 5.0, 200.0, 600.0, 500.0, False)]
    objects, images = make(common)
    out = ss.rare_class(objects, images)
    assert_all_images(out, images)
    assert out["img-train"].value > 0.5
    assert "train" in out["img-train"].reason and "%" in out["img-train"].reason
    assert out["img-0"].value == 0


def test_edge_no_trunc():
    objects, images = make({
        "img-edge": [car(x1=0.0), car(x1=500.0, y1=620.0)],  # chạm mép trái và mép dưới
        "img-trunc": [car(x1=0.0, truncated=True)],
        "img-inside": [car(x1=3.0)],
    })
    out = ss.edge_no_trunc(objects, images)
    assert_all_images(out, images)
    assert out["img-edge"].value == 1.0
    assert "2 box" in out["img-edge"].reason and "mép trái" in out["img-edge"].reason
    assert [e["obj_id"] for e in out["img-edge"].evidence] == ["1", "2"]
    assert "dưới" in out["img-edge"].evidence[1]["note"]
    assert out["img-trunc"].value == 0
    assert out["img-inside"].value == 0


def test_signals_feed_rule_ranking():
    from src.contracts import check_queue
    from src.scoring import rule

    objects, images = bdd100k.to_tables(bdd100k.read_frames(FIXTURE))
    signals = {n: fn(objects, images) for n, fn in ss.SIGNALS.items()}
    queue = rule.rank(signals, {n: 1.0 for n in signals}, "rule-test")
    assert check_queue(queue) == []
    assert len(queue) == len(images)


def test_evidence_box_is_pixel_list():
    objects, images = make({"a": [car(x1=0.0)]})
    assert ss.edge_no_trunc(objects, images)["a"].evidence[0]["box"] == [0.0, 300.0, 80.0, 400.0]
