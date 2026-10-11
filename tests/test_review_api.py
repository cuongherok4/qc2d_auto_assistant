import json

import pandas as pd
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from src.api.main import create_app
from src.api.settings import Settings
from src.contracts import QUEUE_COLS


@pytest.fixture
def setup_review(tmp_path):
    reports = tmp_path / "reports"
    reports.mkdir()
    images = tmp_path / "images"
    images.mkdir()
    queue = reports / "ranked_queue_v1.csv"
    pd.DataFrame(
        [[f"image-{i:02}", 100 - i, i, f"[R1] Cao {i}px (tr.1)", "v1"] for i in range(1, 25)],
        columns=QUEUE_COLS,
    ).to_csv(queue, index=False)
    evidence = reports / "evidence_v1.jsonl"
    evidence.write_text(
        json.dumps(
            {
                "image_id": "image-01",
                "boxes": [
                    {"obj_id": "9", "box": [10, 20, 30, 40], "note": "Cao 20px", "signal": "guideline"}
                ],
            }
        )
        + "\n"
    )
    settings = Settings(
        reports=reports,
        database=tmp_path / "review.db",
        images=images,
        predictions=tmp_path / "preds.parquet",
        mapping=tmp_path / "map.parquet",
        queue_file=queue,
    )
    return settings


def payload(client, image_id="image-01", **values):
    detail = client.get(f"/image/{image_id}").json()
    return {
        "request_id": f"req-{image_id}",
        "image_id": image_id,
        "verdict": "error",
        "reviewer": "Tú Anh",
        "seconds_spent": 12.5,
        "queue_id": detail["queue_id"],
        "model_version": detail["model_version"],
        "rank": detail["rank"],
        **values,
    }


def test_persistence_retry_history_and_stats(setup_review):
    client = TestClient(create_app(setup_review))
    submitted = payload(client, obj_ids=["9"], note="Đã lưu CVAT")
    first = client.post("/verdict", json=submitted)
    assert first.status_code == 200
    assert "is_audit" not in first.json()
    retry = client.post("/verdict", json=submitted)
    assert retry.json()["duplicate"] is True
    assert retry.json()["id"] == first.json()["id"]
    assert client.post("/verdict", json={**submitted, "verdict": "false_alarm"}).status_code == 409
    restarted = TestClient(create_app(setup_review))
    queue = restarted.get("/queue").json()
    assert queue["remaining"] == 23
    assert "image-01" not in {row["image_id"] for row in queue["items"]}
    assert (
        restarted.post(
            "/verdict", json={**submitted, "request_id": "second", "verdict": "false_alarm"}
        ).status_code
        == 200
    )
    stats = restarted.get("/stats").json()
    assert stats["reviewed_images"] == 1 and stats["review_events"] == 2
    assert stats["latest"]["error_rate"] == 0
    assert stats["history"]["error_rate"] == 0.5
    assert stats["history"]["seconds_spent"] == 25
    assert restarted.get("/queue?include_reviewed=true").json()["remaining"] == 24
    with restarted.app.state.store.connection() as db:
        with pytest.raises(Exception, match="append-only"):
            db.execute("UPDATE verdicts SET verdict='skip'")


def test_detail_image_mapping_and_predictions(setup_review):
    setup_review.images.joinpath("image-01.jpg").write_bytes(b"test-jpeg-fixture")
    pd.DataFrame([["image-01", 3, 8, 11]], columns=["image_id", "task_id", "job_id", "frame"]).to_parquet(
        setup_review.mapping, index=False
    )
    pd.DataFrame(
        [["image-01", 10, 20, 30, 40, "car", 0.8]],
        columns=["image_id", "x1", "y1", "x2", "y2", "category", "conf"],
    ).to_parquet(setup_review.predictions, index=False)
    client = TestClient(create_app(setup_review))
    row = client.get("/image/image-01").json()
    assert row["evidence"][0]["obj_id"] == "9"
    assert row["predictions"][0]["conf"] == 0.8
    assert row["cvat_url"] == "http://localhost:8080/tasks/3/jobs/8?frame=11"
    assert row["image_available"]
    assert client.get("/image/image-01/file").content == b"test-jpeg-fixture"
    assert client.get("/image/image-02/file").status_code == 404
    assert client.get("/image/absent").status_code == 404
    with pytest.raises(HTTPException):
        client.app.state.service.image_path("../secret")
    outside = setup_review.images.parent / "secret.jpg"
    outside.write_bytes(b"secret")
    setup_review.images.joinpath("escape.jpg").symlink_to(outside)
    assert client.get("/image/escape/file").status_code == 404


@pytest.mark.parametrize(
    "change",
    [
        {"seconds_spent": -1},
        {"reviewer": " "},
        {"verdict": "bad"},
        {"rank": 0},
        {"obj_ids": [""]},
        {"unexpected": True},
    ],
)
def test_invalid_submission(setup_review, change):
    client = TestClient(create_app(setup_review))
    assert client.post("/verdict", json=payload(client, **change)).status_code == 422
    assert client.get("/stats").json()["review_events"] == 0


def test_stale_context_and_pagination(setup_review):
    client = TestClient(create_app(setup_review))
    assert client.get("/queue?limit=-1").status_code == 422
    assert client.get("/queue?offset=-2").status_code == 422
    assert client.get("/queue?offset=99").json()["items"] == []
    assert client.get("/queue?limit=2&offset=2").json()["items"][0]["rank"] == 3
    original = payload(client)
    assert client.post("/verdict", json={**original, "model_version": "bad"}).status_code == 409
    frame = pd.read_csv(setup_review.queue_file)
    frame.model_version = "v2"
    frame.to_csv(setup_review.queue_file, index=False)
    assert client.post("/verdict", json=original).status_code == 409


def test_empty_corrupt_and_batches(setup_review):
    client = TestClient(create_app(setup_review))
    assert client.get("/queue?batch=unconfigured").status_code == 404
    setup_review.queue_batches["demo"] = str(setup_review.queue_file)
    assert client.get("/queue?batch=demo").json()["batch_id"] == "demo"
    pd.DataFrame(columns=QUEUE_COLS).to_csv(setup_review.queue_file, index=False)
    assert client.get("/queue").json()["items"] == []
    assert client.get("/health").json()["model_version"] is None
    setup_review.queue_file.write_text("bad,columns\n1,2\n")
    assert client.get("/queue").status_code == 503
    assert client.get("/health").status_code == 503


def test_audit_is_unique_stable_hidden_and_pilot_sessions(setup_review):
    client = TestClient(create_app(setup_review))
    items = client.get("/queue").json()["items"]
    assert len({row["image_id"] for row in items}) == 24
    audit_row = items[10]
    assert audit_row["rank"] > 12 and items[11]["rank"] == 11
    assert all("is_audit" not in row for row in items)
    response = client.post("/verdict", json=payload(client, audit_row["image_id"], session_id="pilot-a"))
    assert response.status_code == 200 and "is_audit" not in response.json()
    assert client.app.state.store.records()[0]["is_audit"] is True
    assert client.get("/queue?session_id=pilot-a").json()["remaining"] == 23
    assert client.get("/queue?session_id=pilot-b").json()["remaining"] == 24
    assert client.get("/queue?order=file").json()["items"][10]["rank"] == 11
    assert client.get("/stats").json()["audit_events"] == 1


def test_missing_backend_is_honest(setup_review):
    client = TestClient(create_app(setup_review))
    assert client.get("/model").json()["backend_ready"] is False
    assert client.post("/retrain").status_code == 503
    assert client.post("/model/rollback", json={"model_version": "missing"}).status_code == 404


def test_invalid_optional_sidecars_degrade_without_breaking_queue(setup_review):
    client = TestClient(create_app(setup_review))
    evidence = setup_review.reports / "evidence_v1.jsonl"
    evidence.write_text(
        json.dumps(
            {
                "image_id": "image-01",
                "boxes": [{"obj_id": 9, "box": ["10", 20, 30, 40], "note": "Fixture", "signal": None}],
            }
        )
    )
    assert client.get("/image/image-01").json()["evidence"][0]["obj_id"] == "9"
    evidence.write_text('{"boxes": "corrupt"}')
    setup_review.mapping.write_bytes(b"corrupt parquet")
    response = client.get("/queue")
    assert response.status_code == 200
    assert response.json()["items"][0]["evidence"] == []
    assert len(response.json()["warnings"]) == 2


def test_retrain_counts_events_and_refuses_overwriting_active_queue(setup_review):
    setup_review.retrain_after = 2

    def backend(**kwargs):
        assert len(kwargs["verdicts"]) == 1  # Two review events, one latest training label.
        return {
            "model_version": "v2",
            "queue_file": setup_review.queue_file,
            "validation_split": "val",
            "metric": "recall@20%",
            "recall_before": 0.8,
            "recall_after": 0.9,
        }

    app = create_app(setup_review, retrain_backend=backend)
    app.state.models.maybe_retrain = lambda: None
    client = TestClient(app)
    first = payload(client)
    client.post("/verdict", json=first)
    client.post("/verdict", json=first)  # Retry must not count twice.
    assert client.get("/model").json()["new_verdicts"] == 1
    client.post("/verdict", json={**first, "request_id": "rereview", "verdict": "false_alarm"})
    assert client.get("/model").json()["new_verdicts"] == 2
    assert client.post("/retrain").status_code == 503
    assert client.get("/model").json()["model_version"] == "v1"
    frame = pd.read_csv(setup_review.queue_file)
    frame.loc[0, "risk_score"] = 3
    frame.to_csv(setup_review.queue_file, index=False)
    assert client.get("/queue").status_code == 503  # Pinned serving snapshot cannot be silently replaced.


@pytest.mark.parametrize("after,accepted", [(0.795, True), (0.79, False)])
def test_model_gate_and_rollback(setup_review, after, accepted):
    setup_review.retrain_after = 2
    candidate_path = setup_review.reports / "ranked_queue_v2.csv"

    def backend(**kwargs):
        assert kwargs["validation_split"] == "val" and kwargs["seed"] == 42
        assert len(kwargs["verdicts"]) == 2
        frame = pd.read_csv(setup_review.queue_file)
        frame.model_version = "v2"
        frame.to_csv(candidate_path, index=False)
        return {
            "model_version": "v2",
            "queue_file": candidate_path,
            "validation_split": "val",
            "metric": "recall@20%",
            "recall_before": 0.8,
            "recall_after": after,
        }

    app = create_app(setup_review, retrain_backend=backend)
    app.state.models.maybe_retrain = lambda: None  # Test the same job through the explicit endpoint.
    client = TestClient(app)
    assert client.post("/retrain").status_code == 409
    original = payload(client)
    assert client.post("/verdict", json=original).status_code == 200
    assert client.post("/verdict", json=payload(client, "image-02")).status_code == 200
    result = client.post("/retrain")
    assert result.status_code == 200
    assert result.json()["status"] == ("accepted" if accepted else "rejected")
    assert client.get("/model").json()["model_version"] == ("v2" if accepted else "v1")
    assert client.post("/verdict", json=original).json()["duplicate"] is True
    if accepted:
        assert client.post("/model/rollback", json={"model_version": "v1"}).status_code == 200
        assert client.get("/model").json()["model_version"] == "v1"
        assert TestClient(create_app(setup_review)).get("/model").json()["model_version"] == "v1"
