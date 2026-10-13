import json
import zipfile
from pathlib import Path

import httpx
import pandas as pd
import pytest

from src.api.cvat_import import import_batch
from src.api.fixtures import prepare
from src.api.operations import export_pilot, package_extension
from src.api.settings import Settings
from src.api.store import ReviewStore
from src.contracts import check_preds, check_queue


def test_fixture_assets_match_shared_contract_and_are_marked(tmp_path):
    pytest.importorskip("PIL")
    result = prepare(tmp_path / "samples")
    assert result["fixture"] is True and result["images"] == 3
    assert check_queue(pd.read_csv(result["queue"])) == []
    assert check_preds(pd.read_parquet(tmp_path / "samples/yolo_preds.parquet")) == []
    assert len(list((tmp_path / "samples/images").glob("*.jpg"))) == 3
    assert "M13_DATABASE" in Path(result["environment"]).read_text()
    archive = tmp_path / "extension.zip"
    assert package_extension(archive) == 5
    with zipfile.ZipFile(archive) as zip_file:
        manifest = json.loads(zip_file.read("manifest.json"))
        assert manifest["manifest_version"] == 3
        assert "sidepanel.js" in zip_file.namelist()


@pytest.mark.parametrize("wrong_readback", [False, True])
def test_cvat_import_new_task_frame_alignment_and_readback(tmp_path, wrong_readback):
    pytest.importorskip("PIL")
    result = prepare(tmp_path / "samples")
    folder = tmp_path / "samples"
    meta_names = ["img-night-2.jpg", "img-empty-3.jpg", "img-day-1.jpg"]  # Intentional upload reorder.
    shapes = []

    def handler(request):
        path, method = request.url.path, request.method
        if path == "/api/tasks":
            if method == "GET":
                data = {"count": 0, "results": []}
            else:
                data = {"id": 4}
                assert len(json.loads(request.content)["labels"]) == 10
        elif path == "/api/tasks/4/data":
            assert b"client_files[0]" in request.content and b"img-day-1.jpg" in request.content
            data = {"rq_id": "request:data:4"}
        elif path.startswith("/api/requests/"):
            data = {"status": "finished"}
        elif path == "/api/tasks/4/data/meta":
            data = {"frames": [{"name": name} for name in meta_names]}
        elif path == "/api/labels":
            data = {
                "results": [
                    {"id": i + 1, "name": name, "attributes": []}
                    for i, name in enumerate(["car", "pedestrian", "motorcycle"])
                ]
            }
        elif path == "/api/tasks/4/annotations":
            if method == "PUT":
                shapes.extend(json.loads(request.content)["shapes"])
            data = {"shapes": shapes}
            if method == "GET" and wrong_readback:
                data = json.loads(json.dumps(data))
                data["shapes"][0]["points"][0] += 25
        else:
            return httpx.Response(404)
        return httpx.Response(200, json=data)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        if wrong_readback:
            with pytest.raises(ValueError, match="đọc lại không khớp"):
                import_batch(
                    "http://localhost:8080",
                    Path(result["queue"]),
                    folder / "images",
                    folder / "labels.json",
                    "Fixture test",
                    client=client,
                )
            return
        result = import_batch(
            "http://localhost:8080",
            Path(result["queue"]),
            folder / "images",
            folder / "labels.json",
            "Fixture test",
            client=client,
        )
    assert result["images"] == 3 and result["boxes"] == 3
    car = next(shape for shape in shapes if shape["label_id"] == 1)
    assert car["frame"] == 2  # Uses CVAT metadata, not queue rank or presumed sorting.


def test_cvat_import_never_overwrites_existing_task(tmp_path):
    pytest.importorskip("PIL")
    result = prepare(tmp_path / "samples")
    requested = []

    def handler(request):
        requested.append(request.method)
        return httpx.Response(200, json={"count": 1, "results": [{"id": 9}]})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError, match="đã tồn tại"):
            import_batch(
                "http://localhost:8080",
                Path(result["queue"]),
                tmp_path / "samples/images",
                tmp_path / "samples/labels.json",
                "Existing task",
                client=client,
            )
    assert requested == ["GET"]


def test_pilot_export_preserves_observed_events_and_filters(tmp_path, monkeypatch):
    settings = Settings(database=tmp_path / "verdict.db")
    monkeypatch.setattr(Settings, "configured", lambda: settings)
    store = ReviewStore(settings.database)
    for i, verdict in enumerate(["error", "false_alarm", "skip"]):
        store.append(
            {
                "request_id": str(i),
                "image_id": "fixture-1",
                "verdict": verdict,
                "reviewer": "unit reviewer",
                "seconds_spent": 7 + i,
                "note": "unit fixture",
                "obj_ids": [],
                "batch_id": "batch",
                "queue_id": "queue",
                "model_version": "v1",
                "rank": 1,
                "session_id": "A" if i < 2 else "B",
                "review_order": "priority",
            },
            is_audit=False,
        )
    output = tmp_path / "pilot.csv"
    assert export_pilot(output, reviewer="unit reviewer", session_id="A")["events"] == 0
    result = export_pilot(output, reviewer="unit reviewer", session_id="A", include_development=True)
    assert result["events"] == 2
    session = result["sessions"][0]
    assert session["seconds"] == 15 and session["events"] == 2 and session["images"] == 1
    assert session["true_errors"] == 0  # Latest verdict is false_alarm, previous error remains in CSV.
    rows = pd.read_csv(output)
    assert rows.verdict.tolist() == ["error", "false_alarm"]
    assert output.with_suffix(".summary.json").exists()
