import json

import httpx
import pandas as pd
import pytest

from src.api.cvat_sync import CvatSyncError, sync


def transport(*, duplicate=False, unsafe_next=False, missing=False):
    def respond(request):
        path = request.url.path
        if path == "/api/tasks":
            if request.url.params.get("page") == "2":
                data = {"results": [], "next": None}
            else:
                data = {
                    "results": [{"id": 4}],
                    "next": "https://evil.invalid/tasks"
                    if unsafe_next
                    else "http://localhost:8080/api/tasks?page=2",
                }
        elif path == "/api/jobs":
            data = {
                "results": [
                    {"id": 6, "task_id": 4, "start_frame": 12, "stop_frame": 13, "type": "annotation"},
                    {"id": 7, "type": "ground_truth"},
                ],
                "next": None,
            }
        elif path == "/api/jobs/6/data/meta":
            data = {"frames": [{"name": "nested/a.jpg"}, {"name": "a.png" if duplicate else "b.jpg"}]}
            if missing:
                data["frames"].pop()
        else:
            return httpx.Response(404)
        return httpx.Response(200, json=data)

    return httpx.MockTransport(respond)


def test_paginated_mapping_task_frame_and_missing_report(tmp_path):
    out = tmp_path / "map.parquet"
    with httpx.Client(transport=transport()) as client:
        assert sync("http://localhost:8080", out, image_ids=["a", "b", "absent"], client=client) == 2
    table = pd.read_parquet(out)
    assert table.columns.tolist() == ["image_id", "task_id", "job_id", "frame"]
    assert table.frame.tolist() == [12, 13]
    assert set(table.job_id) == {6}
    assert json.loads(out.with_suffix(".report.json").read_text())["missing"] == ["absent"]


@pytest.mark.parametrize("options", [{"duplicate": True}, {"unsafe_next": True}, {"missing": True}])
def test_unsafe_or_ambiguous_sync_keeps_previous_file(tmp_path, options):
    out = tmp_path / "map.parquet"
    out.write_bytes(b"previous-map")
    with httpx.Client(transport=transport(**options)) as client:
        with pytest.raises(CvatSyncError):
            sync("http://localhost:8080", out, client=client)
    assert out.read_bytes() == b"previous-map"


def test_auth_errors_are_sanitized_and_credentials_required(tmp_path, monkeypatch):
    monkeypatch.delenv("CVAT_USER", raising=False)
    monkeypatch.delenv("CVAT_PASSWORD", raising=False)
    with pytest.raises(CvatSyncError, match="CVAT_USER"):
        sync("http://localhost:8080", tmp_path / "map.parquet")
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(401)))
    with client, pytest.raises(CvatSyncError, match="HTTP 401"):
        sync("http://localhost:8080", tmp_path / "map.parquet", client=client)


def test_default_client_uses_basic_auth(tmp_path, monkeypatch):
    original = httpx.Client
    observed = []

    def respond(request):
        observed.append(request.headers.get("authorization"))
        return httpx.Response(200, json={"results": [], "next": None})

    monkeypatch.setenv("CVAT_USER", "fixture-user")
    monkeypatch.setenv("CVAT_PASSWORD", "fixture-password")
    monkeypatch.setattr(
        httpx, "Client", lambda **kwargs: original(transport=httpx.MockTransport(respond), **kwargs)
    )
    assert sync("http://localhost:8080", tmp_path / "map.parquet") == 0
    assert observed[0].startswith("Basic ")
