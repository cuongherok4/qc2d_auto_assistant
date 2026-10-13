"""Luồng của Cường qua CLI trên dữ liệu tổng hợp: inject -> rank (queue + evidence) -> evaluate -> recheck."""

import json
import random

import pandas as pd
import pytest

from src import cli, config, contracts, pipeline


def _frames(n=60, seed=0):
    rng = random.Random(seed)
    frames = []
    for i in range(n):
        labels = []
        for j in range(rng.randint(1, 12)):
            x, y = rng.uniform(0, 1100), rng.uniform(0, 600)
            w, h = rng.uniform(8, 150), rng.uniform(8, 110)
            labels.append({"id": f"{i}-{j}", "category": rng.choice(["car", "car", "pedestrian", "truck"]),
                           "attributes": {"occluded": False, "truncated": False},
                           "box2d": {"x1": x, "y1": y, "x2": min(1280, x + w), "y2": min(720, y + h)}})
        frames.append({"name": f"img-{i:03d}.jpg", "labels": labels,
                       "attributes": {"weather": rng.choice(["clear", "rainy"]),
                                      "timeofday": rng.choice(["daytime", "night"]), "scene": "city street"}})
    return frames


@pytest.fixture
def flow(tmp_path, monkeypatch):
    real = config.path
    monkeypatch.setattr(config, "path", lambda key: tmp_path / key if key in {
        "injected_dir", "reports_dir"} else real(key))
    labels = tmp_path / "det.json"
    labels.write_text(json.dumps(_frames()), encoding="utf-8")
    assert cli.main(["inject", "--labels", str(labels)]) == 0
    assert cli.main(["rank", "--version", "rule-t1"]) == 0
    return tmp_path


def test_rank_publishes_queue_evidence_and_manifest(flow):
    reports = flow / "reports_dir"
    queue = pd.read_csv(reports / "ranked_queue_rule-t1.csv", dtype={"image_id": str})
    assert contracts.check_queue(queue) == []
    evidence = [json.loads(line) for line in (reports / "evidence_rule-t1.jsonl").read_text().splitlines()]
    assert {r["image_id"] for r in evidence} == set(queue.image_id)
    manifest = json.loads((reports / "ranked_queue_rule-t1.manifest.json").read_text())
    assert manifest["provenance"]["kind"] == "cli_rank" and manifest["n_images"] == 60
    # Không ghi đè phiên bản cũ.
    assert cli.main(["rank", "--version", "rule-t1"]) == 1


def test_evaluate_writes_comparison_and_results(flow):
    queue = flow / "reports_dir" / "ranked_queue_rule-t1.csv"
    assert cli.main(["evaluate", "--queue", str(queue), "--split", "train"]) == 0
    out = flow / "reports_dir" / "eval_rule-t1_train"
    table = pd.read_csv(out / "comparison.csv")
    assert list(table.method) == ["rule-t1", "file_order", "random_mean", "random_std"]
    assert (out / "gain_curve.png").stat().st_size > 0
    row = json.loads((flow / "reports_dir" / "results.jsonl").read_text().splitlines()[-1])
    assert row["model_version"] == "rule-t1" and row["data_kind"] == "synthetic_errors"
    assert row["queue_file"] == str(queue.resolve())


def test_recheck_adapter_rescores_saved_labels(flow, tmp_path):
    reports = flow / "reports_dir"
    manifest_file = reports / "ranked_queue_rule-t1.manifest.json"
    queue = pd.read_csv(reports / "ranked_queue_rule-t1.csv",
                        dtype={"image_id": str, "model_version": str}).fillna("")
    image_id = queue.image_id.iloc[0]
    snapshot = {"image_id": image_id, "width": 1280, "height": 720, "annotation_version": 3,
                "boxes": [{"obj_id": "cvat-1", "category": "car", "box": [100, 100, 300, 260],
                           "attributes": {"occluded": False, "truncated": False}}]}
    result = pipeline.recheck(snapshot=snapshot, queue=queue, output_dir=tmp_path / "re",
                              model_version="recheck-1", seed=42, manifest_file=manifest_file)
    after = pd.read_csv(result["queue_file"], dtype={"image_id": str})
    assert set(after.image_id) == set(queue.image_id) and set(after.model_version) == {"recheck-1"}
    parent = json.loads(manifest_file.read_text())["queue_sha256"]
    assert result["provenance"]["parent_queue_sha256"] == parent
    with pytest.raises(ValueError, match="khác queue"):
        pipeline.recheck(snapshot=snapshot, queue=queue.iloc[::-1], output_dir=tmp_path / "re2",
                         model_version="recheck-2", seed=42, manifest_file=manifest_file)
