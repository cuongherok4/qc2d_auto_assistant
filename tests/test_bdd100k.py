from pathlib import Path

import pytest

from src import config
from src.data import bdd100k

FIXTURE = Path(__file__).parent / "fixtures" / "det_mini.json"


@pytest.fixture
def tables():
    return bdd100k.to_tables(bdd100k.read_frames(FIXTURE))


def test_keeps_empty_images(tables):
    _, images = tables
    assert len(images) == 3
    assert images.set_index("image_id").loc["img-empty-3", "n_boxes"] == 0


def test_maps_old_class_names_and_drops_poly2d(tables):
    objects, _ = tables
    assert set(objects["category"]) == {"car", "pedestrian", "motorcycle"}
    assert len(objects) == 3


def test_geometry_columns(tables):
    objects, _ = tables
    car = objects[objects.category == "car"].iloc[0]
    assert (car.w, car.h, car.area) == (160.0, 120.0, 19200.0)


@pytest.mark.data
def test_real_val_has_10k_images():
    if not config.path("labels_json").exists():
        pytest.skip("chưa có dữ liệu BDD100K")
    _, images = bdd100k.load(use_cache=False)
    assert len(images) == 10_000


def test_has_attribute_columns_tell_missing_from_false():
    frames = [{"name": "a.jpg", "labels": [
        {"id": "1", "category": "car", "attributes": {"occluded": False, "truncated": False},
         "box2d": {"x1": 0, "y1": 0, "x2": 10, "y2": 10}},
        {"id": "2", "category": "car", "box2d": {"x1": 0, "y1": 0, "x2": 10, "y2": 10}},
    ]}]
    objects, _ = bdd100k.to_tables(frames)
    assert objects["has_occluded"].tolist() == [True, False]
    assert objects["has_truncated"].tolist() == [True, False]
    assert objects["occluded"].tolist() == [False, False]


def test_load_rebuilds_cache_missing_new_columns(tmp_path, monkeypatch):
    src = tmp_path / "det_val.json"
    src.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setattr(bdd100k.config, "path", lambda key: tmp_path / "cache")
    objects, _ = bdd100k.load(src)
    (tmp_path / "cache" / "det_val_objects.parquet").unlink()
    objects.drop(columns=["has_occluded"]).to_parquet(tmp_path / "cache" / "det_val_objects.parquet")
    assert "has_occluded" in bdd100k.load(src)[0].columns
