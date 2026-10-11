import pandas as pd
import pytest

from src.contracts import check_preds, check_queue
from src.features.base import SignalResult


def test_signal_result_rejects_out_of_range():
    with pytest.raises(ValueError):
        SignalResult("x", 1.5, "Box car cao 9px")


def test_signal_result_requires_number_in_reason():
    with pytest.raises(ValueError):
        SignalResult("x", 0.5, "Box bất thường")
    assert SignalResult("x", 0.0).reason == ""


def test_queue_contract():
    ok = pd.DataFrame({"image_id": ["a", "b"], "risk_score": [80.0, 10.0], "rank": [1, 2],
                       "top_reasons": ["Ảnh đêm, 23 box", ""], "model_version": ["rule-v0"] * 2})
    assert check_queue(ok) == []
    bad = ok.assign(rank=[2, 1])
    assert any("giảm dần" in e for e in check_queue(bad))


def test_preds_contract():
    ok = pd.DataFrame([["a", 10.0, 10.0, 50.0, 80.0, "car", 0.9]],
                      columns=["image_id", "x1", "y1", "x2", "y2", "category", "conf"])
    assert check_preds(ok) == []
    assert check_preds(ok.assign(category="person"))


def test_samples_follow_contracts(tmp_path, monkeypatch):
    from src import cli, config

    monkeypatch.setattr(config, "ROOT", tmp_path)
    monkeypatch.setattr(config, "path", lambda key: tmp_path / config.load("paths")[key])
    assert cli.main(["samples"]) == 0
    assert check_preds(pd.read_parquet(tmp_path / "data/samples/yolo_preds.parquet")) == []
    assert check_queue(pd.read_csv(tmp_path / "reports/ranked_queue_sample.csv")) == []
