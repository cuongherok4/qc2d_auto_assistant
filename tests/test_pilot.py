"""Synthetic measurements test eligibility/controls; none of these are pilot results."""

import copy
import json

import pytest
from fastapi.testclient import TestClient
from test_recheck import setup_recheck as setup_recheck

from src.api.main import create_app
from src.api.operations import export_pilot
from src.api.pilot import PilotPlan, compare, register
from src.api.saved_labels import SavedLabels
from src.api.service import QueueService
from src.api.settings import Settings
from src.api.store import ReviewStore


def enroll(settings, cvat, **values):
    plan = PilotPlan(
        reviewer="Unit human fixture",
        session_id="unit-human",
        comparison_id="unit-comparison",
        order="priority",
        **values,
    )
    store = ReviewStore(settings.database)
    return register(
        plan,
        confirmed=True,
        settings=settings,
        saved=SavedLabels(settings, QueueService(settings, store), cvat),
    )


def verdict(**values):
    return {
        "request_id": "unit-event",
        "image_id": "image-1",
        "verdict": "error",
        "reviewer": "Unit human fixture",
        "session_id": "unit-human",
        "seconds_spent": 8,
        **values,
    }


def test_pilot_cannot_promote_development_and_freezes_context(setup_recheck, monkeypatch, tmp_path):
    settings, _, _, cvat, _ = setup_recheck
    with pytest.raises(ValueError, match="confirm-human"):
        enroll(settings, cvat)
    settings.data_purpose = "real"  # Unit-only eligibility flag; REST remains mocked.
    manifest = enroll(settings, cvat)
    assert manifest["purpose"] == "human_pilot"
    assert list(map(tuple, manifest["cvat_tasks"])) == [(settings.cvat_url, 4)]
    client = TestClient(create_app(settings, cvat_client=cvat))
    assert client.post("/verdict", json=verdict(review_order="file")).status_code == 409
    assert client.post("/verdict", json=verdict()).status_code == 200
    assert client.post("/verdict", json=verdict()).json()["duplicate"] is True
    assert (
        client.post(
            "/verdict", json=verdict(request_id="automated", reviewer="Automated", session_id="automated")
        ).status_code
        == 200
    )
    monkeypatch.setattr(Settings, "configured", lambda: settings)
    output = tmp_path / "human.csv"
    report = export_pilot(output)
    assert report["events"] == 1 and report["excluded_events"] == 1
    assert report["sessions"][0]["seconds"] == 8
    assert (
        report["sessions"][0]["pilot_manifest"]["annotation_baseline_sha256"]
        == manifest["annotation_baseline_sha256"]
    )
    settings.mapping.write_bytes(b"changed mapping")
    assert client.post("/verdict", json=verdict(request_id="mapping-changed")).status_code == 409
    assert client.post("/verdict", json=verdict()).json()["duplicate"] is True


def test_existing_automatic_events_cannot_be_enrolled(setup_recheck):
    settings, _, _, cvat, _ = setup_recheck
    settings.data_purpose = "real"
    client = TestClient(create_app(settings, cvat_client=cvat))
    assert client.post("/verdict", json=verdict()).status_code == 200
    with pytest.raises(ValueError, match="verdict sẵn"):
        enroll(settings, cvat)


@pytest.mark.parametrize("failure", [None, "development", "snapshot", "labels", "same_reviewer", "same_task"])
def test_comparison_requires_matched_snapshot_initial_labels_and_independent_tasks(
    setup_recheck, monkeypatch, tmp_path, failure
):
    settings, _, _, cvat, _ = setup_recheck
    settings.data_purpose = "real"
    enroll(settings, cvat)
    client = TestClient(create_app(settings, cvat_client=cvat))
    client.post("/verdict", json=verdict())
    monkeypatch.setattr(Settings, "configured", lambda: settings)
    first = tmp_path / "first.csv"
    original = export_pilot(first)
    second = copy.deepcopy(original)
    arm = second["sessions"][0]
    arm["order"] = "file"
    arm["reviewer"] = "Second unit fixture"
    manifest = arm["pilot_manifest"]
    manifest["plan"].update(order="file", reviewer="Second unit fixture")
    manifest["cvat_tasks"][0][1] = 8
    if failure == "development":
        second["include_development"] = True
    elif failure == "snapshot":
        manifest["queue_id"] = "different"
    elif failure == "labels":
        manifest["annotation_baseline_sha256"] = "different"
    elif failure == "same_reviewer":
        manifest["plan"]["reviewer"] = original["sessions"][0]["pilot_manifest"]["plan"]["reviewer"]
    elif failure == "same_task":
        manifest["cvat_tasks"] = original["sessions"][0]["pilot_manifest"]["cvat_tasks"]
    second_path = tmp_path / "second.summary.json"
    second_path.write_text(json.dumps(second))
    if failure:
        with pytest.raises(ValueError):
            compare(first.with_suffix(".summary.json"), second_path, tmp_path / "comparison.json")
    else:
        assert (
            compare(first.with_suffix(".summary.json"), second_path, tmp_path / "comparison.json")[
                "comparison_id"
            ]
            == "unit-comparison"
        )
