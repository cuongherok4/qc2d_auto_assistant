import math

import numpy as np

from src.eval import metrics
from src.features import geometry


def test_metrics_basic():
    ids = [f"img{i:02d}" for i in range(10)]
    errs = [{"image_id": "img00", "type": "missing"}, {"image_id": "img01", "type": "shift"},
            {"image_id": "img09", "type": "missing"}]
    m = metrics.error_mass(errs)
    assert math.isclose(metrics.recall_at(ids, m, 0.2), 1.3 / 2.3)
    perfect = ["img00", "img09", "img01"] + ids[2:9]
    assert metrics.n_to_reach(perfect, m, 0.8) == 2
    assert math.isclose(metrics.ndcg(perfect, m), 1.0)


def test_iou_and_match():
    a = np.array([[0, 0, 10, 10], [20, 20, 30, 30]])
    b = np.array([[0, 0, 10, 10], [5, 5, 15, 15]])
    pairs, unmatched_labels, _ = geometry.match_boxes(a, b)
    assert pairs == [(0, 0, 1.0)] and unmatched_labels == [1]
