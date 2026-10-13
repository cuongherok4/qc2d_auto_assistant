import copy

import pytest
import yaml
from fastapi.testclient import TestClient
from test_guideline import SAMPLES, make_pdf

from src.guideline.editor import create_editor
from src.guideline.extract import extract, load_approved
from src.guideline.schema import ExtractedSpec


@pytest.fixture
def editor(tmp_path):
    source = tmp_path / "source.pdf"
    make_pdf(source, SAMPLES[0]["paragraphs"][1:])
    drafts = tmp_path / "drafts"
    path = extract(source, drafts, options={"cache_dir": str(tmp_path / "cache"),
                   "provider": "fixture", "model": "unit-fixture"},
                   backend=lambda *args: copy.deepcopy(SAMPLES[0]["response"]))
    client = TestClient(create_editor(drafts, tmp_path / "approved", token="test-token"),
                        base_url="http://127.0.0.1")
    client.headers["X-M13-Token"] = "test-token"
    key = client.get("/api/drafts").json()[0]["key"]
    return client, path, key, source


def payload(client, key):
    detail = client.get("/api/drafts/" + key).json()
    spec = detail["spec"]
    raw = {k: v for k, v in spec.items() if k in ExtractedSpec.model_fields}
    raw["rules"] = [{k: v for k, v in r.items() if k != "severity"} for r in raw["rules"]]
    return {"revision": detail["revision"], "reviewer": "Unit fixture reviewer", "content": raw}


def test_editor_auth_origin_path_and_protected_fields(editor):
    client, path, key, _ = editor
    assert client.get("/").status_code == 200
    assert client.get("/api/drafts", headers={"X-M13-Token": "wrong"}).status_code == 403
    assert client.get("/api/drafts", headers={"Origin": "https://foreign.example"}).status_code == 403
    assert client.get("/session", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert client.get("/api/drafts/not-registered").status_code == 404
    before = path.read_bytes()
    value = payload(client, key)
    value["content"]["approved_by"] = "fake"
    assert client.post(f"/api/drafts/{key}/save", json=value).status_code == 422
    assert path.read_bytes() == before


def test_save_keeps_parent_and_records_new_unapproved_revision(editor):
    client, path, key, _ = editor
    before = path.read_bytes()
    value = payload(client, key)
    value["content"]["rules"][0]["message"] = "Reworded fixture message"
    result = client.post(f"/api/drafts/{key}/save", json=value)
    assert result.status_code == 200
    detail = result.json()
    assert path.read_bytes() == before and detail["spec"]["approved_by"] == ""
    assert detail["spec"]["version"] != yaml.safe_load(before)["version"]
    history = detail["spec"]["extraction"]["review_history"]
    assert history[-1]["parent_sha256"] == value["revision"]
    assert detail["problems"] == []
    with pytest.raises(ValueError, match="chưa có người duyệt"):
        load_approved(client.app.state.repo.path(detail["key"]))


def test_bad_quote_schema_and_changed_source_block_save_and_approval(editor):
    client, _, key, source = editor
    value = payload(client, key)
    value["content"]["rules"][0]["quote"] = "invented text"
    assert client.post(f"/api/drafts/{key}/save", json=value).status_code == 422
    value = payload(client, key)
    value["content"]["rules"][0]["check"] = "unsupported"
    assert client.post(f"/api/drafts/{key}/save", json=value).status_code == 422
    source.write_bytes(b"changed source")
    approve = {"revision": value["revision"], "reviewer": "Fixture reviewer", "confirmed": True}
    assert client.post(f"/api/drafts/{key}/approve", json=approve).status_code == 422


def test_fixture_approval_requires_confirmation_and_editing_creates_new_draft(editor):
    client, path, key, _ = editor
    value = payload(client, key)
    request = {"revision": value["revision"], "reviewer": "Fixture test reviewer", "confirmed": False}
    assert client.post(f"/api/drafts/{key}/approve", json=request).status_code == 422
    request["confirmed"] = True
    approved = client.post(f"/api/drafts/{key}/approve", json=request).json()
    assert approved["approved"] is True
    approved_path = client.app.state.repo.path(approved["key"])
    before = approved_path.read_bytes()
    assert load_approved(approved_path)["approved_by"] == "Fixture test reviewer"
    assert yaml.safe_load(path.read_text())["approved_by"] == ""
    new = client.post(f"/api/drafts/{approved['key']}/save", json=payload(client, approved["key"]))
    assert new.status_code == 200 and new.json()["approved"] is False
    assert approved_path.read_bytes() == before


def test_conflicting_file_change_and_symlink_are_rejected(editor, tmp_path):
    client, path, key, _ = editor
    value = payload(client, key)
    path.write_text(path.read_text() + "\n# external edit\n")
    assert client.post(f"/api/drafts/{key}/save", json=value).status_code == 409
    assert client.post(f"/api/drafts/{key}/approve", json={"revision": value["revision"],
                       "reviewer": "Fixture", "confirmed": True}).status_code == 409
    outside = tmp_path / "outside.yaml"
    outside.write_text("private unrelated file")
    (path.parent / "link.yaml").symlink_to(outside)
    assert all(d["filename"] != "link.yaml" for d in client.get("/api/drafts").json())
