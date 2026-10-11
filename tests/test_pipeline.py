"""Chạy thử bước 1 -> 3a -> 4 trên fixture: kiểm các module ghép được với nhau."""
from pathlib import Path

from src.contracts import check_queue
from src.data import bdd100k
from src.features import geometric
from src.scoring import rule

FIXTURE = Path(__file__).parent / "fixtures" / "det_mini.json"


def test_rule_queue_on_fixture():
    objects, images = bdd100k.to_tables(bdd100k.read_frames(FIXTURE))
    signals = {"hard_condition": geometric.hard_condition(objects, images)}
    queue = rule.rank(signals, {"hard_condition": 1.0}, "rule-test")
    assert check_queue(queue) == []
    assert queue.iloc[0]["image_id"] == "img-night-2"
    assert "đêm" in queue.iloc[0]["top_reasons"]
