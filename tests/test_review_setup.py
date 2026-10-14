"""Prepare matched pipeline artifacts; transport tests do not claim real CVAT import."""

import json
import shutil
import stat
import zipfile
from pathlib import Path

import pandas as pd
import pytest
from PIL import Image

from src import cli, config, pipeline
from src.api import review_setup
from src.api.main import create_app
from src.api.settings import Settings


@pytest.fixture
def source(tmp_path):
    root = tmp_path / "input"
    root.mkdir()
    images = root / "images"
    images.mkdir()
    frames = []
    for i in range(3):
        name = f"image-{i}.jpg"
        Image.new("RGB", (1280, 720), (30, 50, 70)).save(images / name)
        frames.append({"name": name, "labels": [{
            "id": i, "category": "car", "attributes": {"truncated": False},
            "box2d": {"x1": 0 if i == 0 else 100, "y1": 20, "x2": 200, "y2": 120},
        }]})
    manifest = pipeline.publish(
        frames, root / "reports", "rule-fixture-prepare", names=["edge_no_trunc"],
        weights={"edge_no_trunc": 1}, options={"signal_options": {}},
        provenance={"kind": "fixture"},
    )
    return root, images, manifest


def prepared(source, output, **kwargs):
    root, images, manifest = source
    return review_setup.prepare(Path(manifest["queue_file"]), images, output,
                                source_root=root, limit=2, **kwargs)


def test_prepare_accepts_published_repo_relative_paths(source, tmp_path, monkeypatch):
    root, _, artifact = source
    manifest_file = Path(artifact["manifest_file"])
    manifest = json.loads(manifest_file.read_text())
    shutil.copytree(config.ROOT / "extension", root.parent / "extension")
    monkeypatch.setattr(config, "ROOT", root.parent)
    for key in ("queue", "labels", "features", "evidence"):
        manifest[key + "_file"] = str(Path(manifest[key + "_file"]).relative_to(root.parent))
    manifest_file.write_text(json.dumps(manifest))
    record = prepared(source, tmp_path / "repo-relative-demo")
    assert record["version"] == "rule-fixture-prepare"


def test_prepare_keeps_snapshot_scores_and_paired_pilot_queue(source, tmp_path):
    a, b = tmp_path / "arm-a", tmp_path / "arm-b"
    record = prepared(source, a)
    prepared(source, b)
    version = record["version"]
    queue = a / f"ranked_queue_{version}.csv"
    assert queue.read_bytes() == (b / queue.name).read_bytes()
    original = pd.read_csv(source[2]["queue_file"]).head(2)
    pd.testing.assert_frame_equal(pd.read_csv(queue), original)
    labels = json.loads((a / f"labels_{version}.json").read_text())
    assert labels[0]["labels"][0]["box2d"]["x1"] == 0
    manifest = json.loads(queue.with_suffix(".manifest.json").read_text())
    assert manifest["n_images"] == 2 and manifest["provenance"]["scores_recomputed"] is False
    for key in ("queue", "labels", "evidence", "features"):
        assert pipeline.sha256(pipeline.located(manifest[key + "_file"])) == manifest[key + "_sha256"]
    assert not (a / "predictions.parquet").exists()  # no invented detector predictions
    env = (a / "runtime.env").read_text()
    assert str(a / "review.db") in env and "CVAT_PASSWORD" not in env
    app = create_app(Settings(queue_file=queue, database=a / "test.db", reports=a,
                              evidence_file=a / f"evidence_{version}.jsonl"))
    assert app.state.service.detail("image-0")["evidence"][0]["box"][0] == 0


def test_rerun_preserves_db_and_rejects_changed_artifacts(source, tmp_path):
    out = tmp_path / "prepared"
    record = prepared(source, out)
    (out / "review.db").write_bytes(b"user verdicts")
    (out / "cvat_map.parquet").write_bytes(b"user mapping")
    assert prepared(source, out) == record
    assert (out / "review.db").read_bytes() == b"user verdicts"
    target = out / f"labels_{record['version']}.json"
    target.write_text("user edits")
    with pytest.raises(ValueError, match="Artifact đã đổi"):
        prepared(source, out)
    assert target.read_text() == "user edits"


def test_snapshot_is_distinguished_from_original_and_config_edits_are_preserved(source, tmp_path):
    labels = json.loads(Path(source[2]["labels_file"]).read_text())
    original = tmp_path / "original.json"
    labels[0]["labels"] = []
    original.write_text(json.dumps(labels))
    out = tmp_path / "prepared"
    record = prepared(source, out, original_labels=original)
    assert record["annotation_kind"] == "changed_from_original"
    snapshot = json.loads((out / f"labels_{record['version']}.json").read_text())
    assert snapshot[0]["labels"]  # imported snapshot, not the other original file
    env = out / "runtime.env"
    env.write_text("export M13_DATABASE=user.db\n")
    with pytest.raises(ValueError, match="runtime.env"):
        prepared(source, out, original_labels=original)
    assert env.read_text() == "export M13_DATABASE=user.db\n"


def test_requested_count_and_source_root_are_enforced(source, tmp_path):
    root, images, manifest = source
    with pytest.raises(ValueError, match="không đủ"):
        review_setup.prepare(Path(manifest["queue_file"]), images, tmp_path / "large",
                             source_root=root, limit=4)
    with pytest.raises(ValueError, match="ngoài bundle"):
        review_setup.prepare(Path(manifest["queue_file"]), images, tmp_path / "foreign",
                             source_root=root / "images", limit=2)


def test_real_requires_the_agreed_original_labels_checksum(source, tmp_path):
    wrong = tmp_path / "det_val.json"
    wrong.write_text("[]")
    with pytest.raises(ValueError, match="Checksum"):
        prepared(source, tmp_path / "real", purpose="real", original_labels=wrong)
    assert not (tmp_path / "real").exists()


def test_missing_image_or_changed_manifest_source_leaves_no_output(source, tmp_path):
    (source[1] / "image-0.jpg").unlink()
    with pytest.raises(ValueError, match="Ảnh thiếu"):
        prepared(source, tmp_path / "missing")
    assert not (tmp_path / "missing").exists()
    Path(source[2]["labels_file"]).write_text("[]")
    with pytest.raises(ValueError, match="sai hash"):
        prepared(source, tmp_path / "changed")


def test_connect_retry_uses_existing_task_and_keeps_mapping(source, tmp_path, monkeypatch):
    out = tmp_path / "prepared"
    prepared(source, out)
    calls = []

    def importer(url, queue, images, labels, name, **kwargs):
        calls.append(name)
        assert json.loads(labels.read_text())[0]["labels"][0]["box2d"]["x1"] == 0
        return {"task_id": 73, "name": name, "images": 2}

    attempts = []

    def sync(url, mapping, *, task_ids, image_ids, **kwargs):
        assert task_ids == [73]
        attempts.append(True)
        if len(attempts) == 1:
            raise ValueError("fixture sync failure")
        pd.DataFrame([[i, 73, 91, f+17] for f, i in enumerate(image_ids)],
                     columns=["image_id", "task_id", "job_id", "frame"]).to_parquet(mapping)
        return len(image_ids)

    monkeypatch.setattr(review_setup, "import_batch", importer)
    monkeypatch.setattr(review_setup, "sync", sync)
    with pytest.raises(ValueError, match="sync failure"):
        review_setup.connect(out, "http://localhost:8080", "fixture task")
    review_setup.connect(out, "http://localhost:8080", "fixture task")
    (out / "review.db").write_bytes(b"user history")
    mapping = (out / "cvat_map.parquet").read_bytes()
    review_setup.connect(out, "http://localhost:8080", "fixture task")
    assert calls == ["fixture task"]
    assert (out / "cvat_map.parquet").read_bytes() == mapping
    assert (out / "review.db").read_bytes() == b"user history"
    with pytest.raises(ValueError, match="task khác"):
        review_setup.connect(out, "http://localhost:8080", "different task")


@pytest.mark.parametrize("name", ["../escape", "/absolute", "data/.env", "data/review.db"])
def test_unpack_rejects_unsafe_or_private_entries(tmp_path, name):
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr(name, "fixture")
    with pytest.raises(ValueError):
        review_setup.unpack(archive, tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_unpack_and_cli_prepare_without_replacing_existing_folder(source, tmp_path):
    archive = tmp_path / "safe.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("data/input.json", "[]")
    assert cli.main(["review-unpack", str(archive), "--out", str(tmp_path / "unpacked")]) == 0
    assert cli.main(["review-unpack", str(archive), "--out", str(tmp_path / "unpacked")]) == 1
    root, images, manifest = source
    assert cli.main(["review-prepare", "--bundle", str(root), "--queue", manifest["queue_file"],
                     "--images", str(images), "--out", str(tmp_path / "cli-out"), "--limit", "2"]) == 0


def test_unpack_rejects_symlink_and_duplicate_paths(tmp_path):
    for kind in ("symlink", "duplicate"):
        archive = tmp_path / f"{kind}.zip"
        with zipfile.ZipFile(archive, "w") as z:
            if kind == "symlink":
                entry = zipfile.ZipInfo("data/link.json")
                entry.external_attr = (stat.S_IFLNK | 0o777) << 16
                z.writestr(entry, "../../outside")
            else:
                z.writestr("data/file.json", "[]")
                with pytest.warns(UserWarning, match="Duplicate"):
                    z.writestr("data/file.json", "{}")
        with pytest.raises(ValueError, match="không an toàn hoặc trùng"):
            review_setup.unpack(archive, tmp_path / kind)


def test_pilot_cli_selects_configured_source_without_enrolling_a_human(source, tmp_path, monkeypatch):
    root, images, manifest = source
    load = config.load
    cfg = {**load("review_acceptance"), "pilot_images": 2,
           "pilot_queue_version": manifest["model_version"]}
    monkeypatch.setattr(config, "load", lambda name: cfg if name == "review_acceptance" else load(name))
    out = tmp_path / "pilot-prepared"
    assert cli.main(["review-prepare", "--bundle", str(root), "--images", str(images),
                     "--out", str(out), "--pilot"]) == 0
    record = review_setup.verify(out)
    assert record["identity"]["role"] == "pilot" and record["images"] == 2
    assert record["purpose"] == "development"
    assert not (out / "review.db").exists() and "human_confirmed" not in record
