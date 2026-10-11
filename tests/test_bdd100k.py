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
