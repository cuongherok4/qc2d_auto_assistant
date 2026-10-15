import json
import shutil
import zipfile

import httpx
import pandas as pd
import pytest

from src.api.cvat_install import prepare_install, restore_source
from src.api.demo_setup import connect_demo, pack_demo, prepare_demo


def test_install_isolates_containers_ports_network_and_volumes(tmp_path):
    import yaml

    out = tmp_path / "install"
    prepare_install(out, project="m13_test", port=18082)
    compose = yaml.safe_load((out / "docker-compose.yml").read_text())
    assert compose["name"] == "m13_test"
    assert all("container_name" not in s for s in compose["services"].values())
    assert compose["services"]["cvat_server"]["image"] == "cvat/server:v2.74.1"
    router = compose["services"]["traefik"]
    assert router["ports"] == ["127.0.0.1:18082:8080"]
    assert "m13_test" in router["environment"]["TRAEFIK_PROVIDERS_DOCKER_CONSTRAINTS"]
    assert router["environment"]["TRAEFIK_PROVIDERS_DOCKER_NETWORK"] == "m13_test_cvat"
    assert all(not (v or {}).get("external") for v in compose["volumes"].values())
    assert prepare_install(out, project="m13_test", port=18082)["fresh_start_verified"] is False
    (out / "docker-compose.yml").write_text("user changes")
    with pytest.raises(ValueError, match="đã sửa"):
        prepare_install(out, project="m13_test", port=18082)
    with pytest.raises(ValueError, match="project mới"):
        prepare_install(tmp_path / "other", project="m13_qc2d")


def test_demo_move_rerun_preserves_db_and_rebases_paths(tmp_path):
    folder = tmp_path / "demo"
    prepare_demo(folder)
    (folder / "review.db").write_bytes(b"user database")
    moved = tmp_path / "moved with spaces"
    shutil.move(folder, moved)
    prepare_demo(moved)
    assert (moved / "review.db").read_bytes() == b"user database"
    assert str(moved) in (moved / "demo.env").read_text()
    with zipfile.ZipFile(moved / "extension.zip") as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert set(archive.namelist()) == {
            "manifest.json", "background.js", "sidepanel.js", "sidepanel.html", "sidepanel.css",
            "content.js", "overlay.js", "logo.svg", *manifest["icons"].values(),
        }
    (moved / "ranked_queue.csv").write_text("edited queue")
    with pytest.raises(ValueError, match="đã đổi"):
        prepare_demo(moved)
    assert (moved / "ranked_queue.csv").read_text() == "edited queue"


def test_manual_demo_no_detector_and_no_label_fabrication(tmp_path):
    from PIL import Image

    image = tmp_path / "test.png"
    Image.new("RGB", (1280, 720)).save(image)
    folder = tmp_path / "manual"
    manifest = prepare_demo(folder, image=image)
    assert manifest["identity"]["kind"] == "manual-unscored" and manifest["real_detector"] is False
    assert not (folder / "predictions.parquet").exists()
    assert json.loads((folder / "labels.json").read_text())[0]["labels"] == []
    assert pd.read_csv(folder / "ranked_queue.csv").model_version.iloc[0] == "manual-unscored-v1"
    from src.contracts import check_queue

    assert check_queue(pd.read_csv(folder / "ranked_queue.csv")) == []
    (folder / "demo.env").write_text("user configuration")
    with pytest.raises(ValueError, match="sửa tay"):
        prepare_demo(folder, image=image)


def test_connect_resumes_actual_task_mapping_readonly_after_failed_sync(tmp_path, monkeypatch):
    folder = tmp_path / "demo"
    prepare_demo(folder)
    imports = []

    def importer(*args, **kwargs):
        imports.append(True)
        return {"task_id": 73, "name": "Test task", "images": 3}

    monkeypatch.setattr("src.api.demo_setup.import_batch", importer)
    requests = []
    incomplete = True

    def handler(request):
        requests.append(request.method)
        if request.url.path == "/api/jobs":
            data = {"results": [{"id": 91, "task_id": 73, "start_frame": 5, "stop_frame": 7}], "next": None}
        else:
            names = ["img-empty-3.jpg", "img-day-1.jpg", "img-night-2.jpg"]
            if incomplete:
                names[0] = "wrong.jpg"
            data = {"frames": [{"name": n} for n in names]}
        return httpx.Response(200, json=data)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError, match="thiếu ảnh"):
            connect_demo(folder, "http://localhost:8080", "Test task", client=client)
        incomplete = False
        connect_demo(folder, "http://localhost:8080", "Test task", client=client)
        mapping = pd.read_parquet(folder / "cvat_map.parquet")
        assert set(mapping.task_id) == {73} and set(mapping.job_id) == {91}
        assert mapping.set_index("image_id").loc["img-day-1", "frame"] == 6
        (folder / "review.db").write_bytes(b"saved verdicts")
        connect_demo(folder, "http://localhost:8080", "Test task", client=client)
        assert (folder / "review.db").read_bytes() == b"saved verdicts"
        assert len(imports) == 1 and set(requests) == {"GET"}
        mapping.loc[0, "frame"] = 99
        mapping.to_parquet(folder / "cvat_map.parquet", index=False)
        with pytest.raises(ValueError, match="Mapping đã thay đổi"):
            connect_demo(folder, "http://localhost:8080", "Test task", client=client)


def test_package_excludes_machine_secrets_database_mapping_and_can_be_reprepared(tmp_path):
    folder = tmp_path / "demo"
    prepare_demo(folder)
    (folder / "account.env").write_text("CVAT_PASSWORD=unit-private")
    (folder / "review.db").write_bytes(b"private records")
    (folder / "cvat_map.parquet").write_bytes(b"machine IDs")
    manifest = json.loads((folder / "demo.json").read_text())
    manifest["cvat"] = {"task_id": 91, "url": "http://localhost:8080"}
    (folder / "demo.json").write_text(json.dumps(manifest))
    output = tmp_path / "demo.zip"
    pack_demo(folder, output)
    with zipfile.ZipFile(output) as archive:
        assert not {"account.env", "review.db", "cvat_map.parquet", "demo.env"} & set(archive.namelist())
        assert "cvat" not in json.loads(archive.read("demo.json"))
        archive.extractall(tmp_path / "other-machine")
    prepare_demo(tmp_path / "other-machine")
    assert (tmp_path / "other-machine/demo.env").is_file()


def test_restore_only_missing_files_and_empty_docker_placeholders(tmp_path):
    target = tmp_path / "old-source"
    (target / "components/analytics/grafana_conf.yml").mkdir(parents=True)
    restored = restore_source(target)
    assert restored["restored_files"] == 3
    assert restore_source(target)["restored_files"] == 0
    (target / "docker-compose.yml").write_text("user compose")
    with pytest.raises(ValueError, match="không ghi đè"):
        restore_source(target)
    assert (target / "docker-compose.yml").read_text() == "user compose"
