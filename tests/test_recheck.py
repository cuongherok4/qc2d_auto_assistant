"""Fixtures validate data flow; this test backend is not a production QC detector."""

import copy
import json

import httpx
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from src.api.main import create_app
from src.api.settings import Settings
from src.contracts import QUEUE_COLS


@pytest.fixture
def setup_recheck(tmp_path):
    queue = tmp_path / "ranked_queue_v1.csv"
    pd.DataFrame(
        [["image-1", 80, 1, "FIXTURE: có 1 box", "v1"], ["image-2", 20, 2, "FIXTURE: có 0 box", "v1"]],
        columns=QUEUE_COLS,
    ).to_csv(queue, index=False)
    evidence = tmp_path / "evidence_v1.jsonl"
    evidence.write_text("\n".join(json.dumps({"image_id": k, "boxes": []}) for k in ["image-1", "image-2"]))
    mapping = tmp_path / "map.parquet"
    pd.DataFrame(
        [["image-1", 4, 6, 12], ["image-2", 4, 6, 13]], columns=["image_id", "task_id", "job_id", "frame"]
    ).to_parquet(mapping)
    settings = Settings(
        queue_file=queue,
        reports=tmp_path,
        database=tmp_path / "review.db",
        mapping=mapping,
        images=tmp_path,
        predictions=tmp_path / "absent.parquet",
        snapshot_dir=str(tmp_path / "snapshots"),
        recheck_dir=str(tmp_path / "rechecks"),
    )
    state = {
        "version": 2,
        "shapes": [
            {
                "id": 7,
                "frame": 12,
                "label_id": 9,
                "type": "rectangle",
                "points": [10, 20, 30, 50],
                "occluded": False,
                "rotation": 0,
                "attributes": [{"spec_id": 44, "value": "false"}],
            }
        ],
        "tracks": [],
        "tags": [],
    }
    options = {"name": "image-1.jpg", "width": 1280, "height": 720}
    observed = []

    def handler(request):
        observed.append(request.method)
        path = request.url.path
        if path == "/api/jobs/6":
            data = {"task_id": 4, "type": "annotation", "start_frame": 12, "stop_frame": 13}
        elif path == "/api/jobs/6/data/meta":
            data = {"frames": [options, {"name": "image-2.jpg", "width": 1280, "height": 720}]}
        elif path == "/api/labels":
            data = {
                "results": [
                    {
                        "id": 9,
                        "name": "car",
                        "attributes": [{"id": 44, "name": "truncated", "input_type": "checkbox"}],
                    }
                ],
                "next": None,
            }
        elif path == "/api/jobs/6/annotations":
            data = copy.deepcopy(state)
        else:
            return httpx.Response(404)
        return httpx.Response(200, json=data)

    cvat = httpx.Client(transport=httpx.MockTransport(handler))
    yield settings, state, options, cvat, observed
    cvat.close()


def request(client, image_id="image-1", request_id="recheck-1"):
    saved = client.get(f"/image/{image_id}/saved")
    assert saved.status_code == 200, saved.text
    value = saved.json()
    return {"request_id": request_id, "snapshot_id": value["snapshot_id"], "queue_id": value["queue_id"]}


def fixture_backend(*, snapshot, queue, output_dir, model_version, seed):
    assert seed == 42 and snapshot["image_id"] == "image-1"
    assert snapshot["boxes"][0]["attributes"]["truncated"] is False
    # Coordinate-dependent fixture to prove CVAT inputs, not stale queue inputs, reach the callable.
    score = snapshot["boxes"][0]["box"][0]
    queue.loc[queue.image_id == snapshot["image_id"], "risk_score"] = score
    queue.loc[queue.image_id == snapshot["image_id"], "top_reasons"] = f"FIXTURE: x1={score}px"
    queue = queue.sort_values(["risk_score", "image_id"], ascending=[False, True])
    queue["rank"] = range(1, len(queue) + 1)
    queue["model_version"] = model_version
    path = output_dir / f"ranked_queue_{model_version}.csv"
    queue.to_csv(path, index=False)
    evidence = output_dir / f"evidence_{model_version}.jsonl"
    rows = []
    for image in queue.image_id:
        boxes = (
            [
                {"obj_id": b["obj_id"], "box": b["box"], "note": "FIXTURE: nhãn CVAT vừa Save"}
                for b in snapshot["boxes"]
            ]
            if image == snapshot["image_id"]
            else []
        )
        rows.append(json.dumps({"image_id": image, "boxes": boxes}))
    evidence.write_text("\n".join(rows))
    return {"queue_file": path, "evidence_file": evidence}


def test_saved_box_order_matches_cvat_response_and_preserves_object_identity(setup_recheck):
    settings, state, _, cvat, observed = setup_recheck
    original = state["shapes"][0]
    state["shapes"] = [
        {**copy.deepcopy(original), "id": 16, "points": [100, 20, 130, 50]},
        {**copy.deepcopy(original), "id": 2, "points": [200, 20, 230, 50]},
        {**copy.deepcopy(original), "id": 10, "points": [300, 20, 330, 50]},
        {**copy.deepcopy(original), "id": 1, "frame": 13},
    ]
    client = TestClient(create_app(settings, cvat_client=cvat))
    saved = client.get("/image/image-1/saved").json()
    assert [box["obj_id"] for box in saved["boxes"]] == ["16", "2", "10"]
    assert [box["box"][0] for box in saved["boxes"]] == [100, 200, 300]
    assert saved["box_count"] == 3
    assert client.get("/image/image-1/saved").json()["snapshot_id"] == saved["snapshot_id"]
    assert set(observed) == {"GET"}


def test_saved_capture_reads_live_persisted_boxes_and_missing_backend_is_honest(setup_recheck):
    settings, state, _, cvat, observed = setup_recheck
    client = TestClient(create_app(settings, cvat_client=cvat))
    first = client.get("/image/image-1/saved").json()
    assert first["backend_ready"] is False and first["boxes"][0]["box"] == [10, 20, 30, 50]
    assert client.get("/image/image-1/saved").json()["snapshot_id"] == first["snapshot_id"]
    state["shapes"][0]["points"] = [70, 20, 90, 50]
    state["version"] += 1
    second = client.get("/image/image-1/saved").json()
    assert second["snapshot_id"] != first["snapshot_id"] and second["boxes"][0]["box"][0] == 70
    assert set(observed) == {"GET"}  # No CVAT annotation write.
    body = request(client)
    assert client.post("/image/image-1/recheck", json=body).status_code == 503
    assert client.get("/image/image-1").json()["risk_score"] == 80


@pytest.mark.parametrize("problem", ["name", "dimensions", "tracks", "rotation", "inverted"])
def test_capture_refuses_incompatible_mapping_shapes_and_track_data(setup_recheck, problem):
    settings, state, options, cvat, _ = setup_recheck
    if problem == "name":
        options["name"] = "different.jpg"
    elif problem == "dimensions":
        options["width"] = 640
    elif problem == "tracks":
        state["tracks"] = [{"id": 99}]
    elif problem == "rotation":
        state["shapes"][0]["rotation"] = 5
    else:
        state["shapes"][0]["points"] = [90, 0, 10, 50]
    client = TestClient(create_app(settings, cvat_client=cvat))
    assert client.get("/image/image-1/saved").status_code == 503
    assert client.get("/image/image-1").json()["risk_score"] == 80


def test_recheck_publishes_new_queue_and_evidence_keeps_history_and_replays_request(setup_recheck):
    settings, state, _, cvat, _ = setup_recheck
    client = TestClient(create_app(settings, cvat_client=cvat, recheck_backend=fixture_backend))
    before = settings.queue_file.read_bytes()
    verdict = {
        "request_id": "verdict-before",
        "image_id": "image-1",
        "verdict": "error",
        "reviewer": "Fixture",
        "seconds_spent": 0,
    }
    assert client.post("/verdict", json=verdict).status_code == 200
    state["shapes"][0]["points"] = [70, 20, 90, 50]
    body = request(client)
    response = client.post("/image/image-1/recheck", json=body)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["risk_before"] == 80 and result["risk_after"] == 70
    assert result["queue_id"] != result["previous_queue_id"] and settings.queue_file.read_bytes() == before
    detail = client.get("/image/image-1").json()
    assert detail["evidence"][0]["box"][0] == 70 and detail["queue_id"] == result["queue_id"]
    assert client.post("/image/image-1/recheck", json=body).json() == result
    assert client.get("/rechecks/recheck-1").json()["status"] == "completed"
    assert client.post("/image/image-1/recheck", json={**body, "snapshot_id": "0" * 64}).status_code == 409
    assert client.app.state.store.records()[0]["model_version"] == "v1"
    assert client.get("/stats").json()["review_events"] == 0
    assert client.get("/stats", params={"queue_id": result["previous_queue_id"]}).json()["review_events"] == 1
    assert client.get("/stats", params={"queue_id": "0" * 64}).status_code == 404
    assert client.post("/verdict", json=verdict).json()["duplicate"] is True
    restarted = TestClient(create_app(settings, cvat_client=cvat))
    assert restarted.get("/image/image-1").json()["risk_score"] == 70
    assert restarted.post("/model/rollback", json={"model_version": "v1"}).status_code == 200
    assert restarted.get("/image/image-1").json()["risk_score"] == 80


def test_restart_marks_interrupted_recheck_failed_without_publishing(setup_recheck):
    settings, _, _, cvat, _ = setup_recheck
    client = TestClient(create_app(settings, cvat_client=cvat, recheck_backend=fixture_backend))
    body = request(client)
    client.app.state.store.state(
        "recheck:recheck-1", {"status": "running", "input": {"image_id": "image-1", **body}}
    )
    restarted = TestClient(create_app(settings, cvat_client=cvat, recheck_backend=fixture_backend))
    status = restarted.get("/rechecks/recheck-1").json()
    assert status["status"] == "failed" and "bị ngắt" in status["error"]
    assert restarted.get("/image/image-1").json()["risk_score"] == 80
    assert restarted.post("/image/image-1/recheck", json=body).status_code == 409


@pytest.mark.parametrize(
    "failure", ["stale_label", "exception", "wrong_artifact", "label_changes_during_backend"]
)
def test_recheck_refuses_stale_or_failed_jobs_without_activation(setup_recheck, failure):
    settings, state, _, cvat, _ = setup_recheck

    def backend(**kwargs):
        if failure == "exception":
            raise RuntimeError("Fixture backend failure")
        if failure == "wrong_artifact":
            return {"queue_file": settings.queue_file, "evidence_file": settings.queue_file}
        result = fixture_backend(**kwargs)
        if failure == "label_changes_during_backend":
            state["version"] += 1
        return result

    client = TestClient(create_app(settings, cvat_client=cvat, recheck_backend=backend))
    body = request(client)
    if failure == "stale_label":
        state["version"] += 1
    response = client.post("/image/image-1/recheck", json=body)
    assert response.status_code == (409 if failure == "stale_label" else 503)
    assert client.get("/image/image-1").json()["risk_score"] == 80
    assert client.app.state.store.state("model") is None
    if failure != "stale_label":
        assert client.get("/rechecks/recheck-1").json()["status"] == "failed"
