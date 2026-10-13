"""GBM: học trên train, early stop val, queue đúng quy ước, lý do lấy từ tín hiệu, cổng học lại."""

import json

import pandas as pd
import pytest

from src import cli, config, contracts
from src.features.base import SignalResult
from src.scoring import gbm
from tests.test_cli_flow import _frames


def test_train_gbm_cli_publishes_valid_queue(tmp_path, monkeypatch):
    pytest.importorskip("lightgbm")  # extra `gbm`: uv pip install -e ".[gbm]"
    real = config.path
    monkeypatch.setattr(config, "path", lambda key: tmp_path / key if key in {
        "injected_dir", "reports_dir", "models_dir"} else real(key))
    real_load = config.load
    small = {"num_leaves": 4, "min_data_in_leaf": 2, "n_estimators": 30, "early_stopping_rounds": 10,
             "seed": 42}
    monkeypatch.setattr(config, "load", lambda name: {**real_load(name), "gbm": small}
                        if name == "learning" else real_load(name))
    labels = tmp_path / "det.json"
    labels.write_text(json.dumps(_frames(n=200)), encoding="utf-8")
    assert cli.main(["inject", "--labels", str(labels)]) == 0
    assert cli.main(["train-gbm", "--version", "gbm-t1"]) == 0
    queue = pd.read_csv(tmp_path / "reports_dir" / "ranked_queue_gbm-t1.csv", dtype={"image_id": str})
    assert contracts.check_queue(queue) == [] and len(queue) == 200
    manifest = json.loads((tmp_path / "reports_dir" / "ranked_queue_gbm-t1.manifest.json").read_text())
    assert manifest["method"] == "gbm" and manifest["scorer"]["n_train"] > manifest["scorer"]["n_val"] > 0
    assert (tmp_path / "models_dir" / "gbm_gbm-t1.txt").exists()
    assert cli.main(["train-gbm", "--version", "gbm-t1"]) == 1  # không ghi đè


def test_reasons_follow_contribution_and_ties_by_image_id():
    signals = {"a": {"x": SignalResult("a", 0.5, "lý do a 1"), "y": SignalResult("a", 0.0)},
               "b": {"x": SignalResult("b", 0.9, "lý do b 2"), "y": SignalResult("b", 0.0)}}
    contrib = pd.DataFrame({"a": [0.3, 0.0], "b": [-0.1, 0.0]}, index=["x", "y"])
    queue = gbm.queue_from_scores(pd.Series({"y": 0.5, "x": 0.5}), contrib, signals, "gbm-t")
    assert list(queue.image_id) == ["x", "y"] and queue.top_reasons[0] == "lý do a 1"
    assert queue.top_reasons[1] == ""


def test_retrain_gate():
    features = pd.DataFrame({"f": [3.0, 2.0, 1.0, 0.0, 0.0]}, index=list("abcde"))
    mass = pd.Series([1.0, 0, 0, 0, 0], index=list("abcde"))
    good, bad = (lambda X: X["f"].values), (lambda X: -X["f"].values)
    assert gbm.retrain_gate(good, bad, (features, mass))
    assert not gbm.retrain_gate(bad, good, (features, mass))
