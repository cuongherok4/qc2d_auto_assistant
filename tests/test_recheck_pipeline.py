"""Real rule scoring through the API; only CVAT transport and labels are fixtures."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src import pipeline
from src.api.main import create_app
from src.api.settings import Settings
from tests import test_recheck

setup_recheck = test_recheck.setup_recheck


@pytest.fixture
def pipeline_case(setup_recheck, tmp_path, monkeypatch):
    settings, state, _, cvat, _ = setup_recheck
    state["shapes"][0]["points"] = [0, 20, 30, 50]
    frames = [
        {"name": "image-1.jpg", "labels": [{
            "id": "7", "category": "car",
            "box2d": {"x1": 0, "y1": 20, "x2": 30, "y2": 50},
            "attributes": {"occluded": False, "truncated": False},
        }]},
        {"name": "image-2.jpg", "labels": []},
    ]
    artifact = pipeline.publish(
        frames, tmp_path / "source", "rule-integration-fixture",
        names=["edge_no_trunc"], weights={"edge_no_trunc": 1},
        options={"signal_options": {"edge_no_trunc": {"margin": 2, "saturate": 1}}},
        provenance={"kind": "integration_fixture"},
    )
    settings.queue_file = Path(artifact["queue_file"])
    settings.evidence_file = Path(artifact["evidence_file"])
    settings.recheck_backend = "src.pipeline:recheck"

    def forbidden_global_settings(cls):
        raise AssertionError("Recheck must use this API's active queue, not global settings")

    monkeypatch.setattr(Settings, "configured", classmethod(forbidden_global_settings))
    return settings, state, cvat, artifact


def test_api_real_pipeline_rescores_saved_labels_and_continues_after_restart(pipeline_case):
    settings, state, cvat, artifact = pipeline_case
    original = {key: Path(artifact[key]).read_bytes() for key in (
        "queue_file", "evidence_file", "labels_file", "features_file", "manifest_file"
    )}
    app = create_app(settings, cvat_client=cvat)
    with TestClient(app) as client:
        assert client.get("/image/image-1").json()["risk_score"] == 100
        assert client.post("/verdict", json={
            "image_id": "image-1", "verdict": "error", "reviewer": "integration-fixture",
            "seconds_spent": 1, "request_id": "fixture-verdict",
        }).status_code == 200
        stats = client.get("/stats").json()
        # The fixture server now represents annotations saved by CVAT.
        state["shapes"][0]["points"] = [10, 20, 30, 50]
        state["version"] += 1
        body = test_recheck.request(client, request_id="first-real-rule")
        response = client.post("/image/image-1/recheck", json=body)
        assert response.status_code == 200, response.text
        first = response.json()
        assert (first["risk_before"], first["risk_after"]) == (100, 0)
        assert first["score_changed"] is True
        assert client.get("/image/image-1").json()["evidence"] == []
        assert client.get("/stats", params={"queue_id": stats["queue_id"]}).json() == stats
        assert client.post("/image/image-1/recheck", json=body).json() == first
        active_queue = Path(app.state.store.state("model")["queue_file"])
        after_manifest = json.loads(active_queue.with_suffix(".manifest.json").read_text())
        labels = json.loads(Path(after_manifest["labels_file"]).read_text())
        assert labels[0]["labels"][0]["box2d"]["x1"] == 10
        assert labels[1]["labels"] == []

    with TestClient(create_app(settings, cvat_client=cvat)) as restarted:
        assert restarted.get("/model").json()["model_version"] == first["model_version"]
        state["shapes"][0]["points"] = [0, 20, 30, 50]
        state["version"] += 1
        body = test_recheck.request(restarted, request_id="second-real-rule")
        response = restarted.post("/image/image-1/recheck", json=body)
        assert response.status_code == 200, response.text
        second = response.json()
        assert (second["risk_before"], second["risk_after"]) == (0, 100)
        assert second["model_version"] != first["model_version"]
        assert restarted.get("/image/image-1").json()["evidence"][0]["box"][0] == 0
        assert restarted.get("/stats", params={"queue_id": stats["queue_id"]}).json() == stats
    for key, content in original.items():
        assert Path(artifact[key]).read_bytes() == content


def test_missing_manifest_disables_recheck_and_preserves_queue(pipeline_case):
    settings, _, cvat, artifact = pipeline_case
    Path(artifact["manifest_file"]).unlink()
    original = settings.queue_file.read_bytes()
    with TestClient(create_app(settings, cvat_client=cvat)) as client:
        saved = client.get("/image/image-1/saved").json()
        assert saved["backend_ready"] is False
        assert "manifest" in saved["backend_message"]
        response = client.post("/image/image-1/recheck", json={
            "request_id": "no-manifest", "queue_id": saved["queue_id"],
            "snapshot_id": saved["snapshot_id"],
        })
        assert response.status_code == 503
        assert "manifest" in response.json()["detail"]
        assert client.get("/image/image-1").json()["risk_score"] == 100
    assert settings.queue_file.read_bytes() == original


def test_health_only_reports_checks_from_matching_manifest(pipeline_case):
    settings, _, cvat, artifact = pipeline_case
    path = Path(artifact["manifest_file"])
    with TestClient(create_app(settings, cvat_client=cvat)) as client:
        health = client.get("/health").json()
        assert health["active_checks"] == ["edge_no_trunc"]
        assert health["data_purpose"] == "development"
        assert "queue_file" not in health
        manifest = json.loads(path.read_text())
        manifest["queue_sha256"] = "invalid"
        path.write_text(json.dumps(manifest))
        assert client.get("/health").json()["active_checks"] == []
        path.write_text("[]")
        assert client.get("/health").json()["active_checks"] == []


def test_changed_source_artifact_cannot_activate_a_new_queue(pipeline_case):
    settings, _, cvat, artifact = pipeline_case
    with TestClient(create_app(settings, cvat_client=cvat)) as client:
        body = test_recheck.request(client, request_id="changed-source")
        Path(artifact["labels_file"]).write_text("[]")
        response = client.post("/image/image-1/recheck", json=body)
        assert response.status_code == 503
        assert client.get("/rechecks/changed-source").json()["status"] == "failed"
        assert client.get("/model").json()["model_version"] == "rule-integration-fixture"
        assert client.get("/image/image-1").json()["risk_score"] == 100
