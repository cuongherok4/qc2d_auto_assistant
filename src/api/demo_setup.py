"""Repeatable demo preparation/import; user annotations and databases are never reset."""

from __future__ import annotations

import json
import re
import shlex
import shutil
import tempfile
import zipfile
from pathlib import Path

import pandas as pd

from src import contracts
from src.api.cvat_import import import_batch
from src.api.cvat_install import sha
from src.api.cvat_sync import sync
from src.api.fixtures import prepare
from src.api.operations import package_extension
from src.api.saved_labels import atomic_json


def verify(folder: Path) -> dict:
    manifest = json.loads((folder / "demo.json").read_text())
    for name, digest in manifest["files"].items():
        path = folder / name
        if not path.is_file() or not path.resolve().is_relative_to(folder.resolve()) or sha(path) != digest:
            raise ValueError(f"Demo đã đổi/mất đầu vào {name}; không ghi đè, dùng thư mục mới")
    return manifest


def environment(folder: Path, cvat_url: str = "http://localhost:8080"):
    # Paths are regenerated after moving the folder; shell quoting supports spaces.
    files = {"IMAGES": "images", "QUEUE_FILE": "ranked_queue.csv", "EVIDENCE_FILE": "evidence.jsonl",
             "MAPPING": "cvat_map.parquet", "DATABASE": "review.db", "PREDICTIONS": "predictions.parquet",
             "REPORTS": "reports", "SNAPSHOT_DIR": "snapshots", "RECHECK_DIR": "rechecks"}
    values = {"M13_" + key: str((folder / name).resolve()) for key, name in files.items()}
    values.update(M13_CVAT_URL=cvat_url, M13_DATA_PURPOSE="development")
    manifest = json.loads((folder / "demo.json").read_text())
    env = folder / "demo.env"
    if env.exists() and sha(env) != manifest.get("environment_sha256"):
        raise ValueError("demo.env đã sửa tay; giữ nguyên, không tự ghi đè")
    env.write_text("\n".join(f"export {k}={shlex.quote(v)}" for k, v in values.items()) + "\n")
    manifest["environment_sha256"] = sha(env)
    atomic_json(folder / "demo.json", manifest)


def prepare_demo(folder: Path, *, image: Path | None = None) -> dict:
    from PIL import Image

    folder = folder.resolve()
    identity = {"kind": "manual-unscored" if image else "fixture",
                "source_sha256": sha(image) if image else None}
    if folder.exists():
        manifest = verify(folder)
        if image is not None and manifest["identity"] != identity:
            raise ValueError("Demo khác nguồn/loại; chọn thư mục mới")
        environment(folder, manifest.get("cvat", {}).get("url", "http://localhost:8080"))
        return manifest
    folder.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=folder.parent) as temp:
        stage = Path(temp) / "demo"
        stage.mkdir()
        if image:
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,199}", image.stem):
                raise ValueError("Tên ảnh cần image_id an toàn")
            with Image.open(image) as photo:
                if photo.size != (contracts.IMG_W, contracts.IMG_H) or photo.format not in {"JPEG", "PNG"}:
                    raise ValueError("Demo manual cần ảnh JPEG/PNG 1280×720")
                suffix = ".jpg" if photo.format == "JPEG" else ".png"
            (stage / "images").mkdir()
            shutil.copyfile(image, stage / "images" / (image.stem + suffix))
            reason = f"Ảnh {contracts.IMG_W}×{contracts.IMG_H} chưa chấm QC"
            pd.DataFrame([[image.stem, 0, 1, reason, "manual-unscored-v1"]],
                         columns=contracts.QUEUE_COLS).to_csv(stage / "ranked_queue.csv", index=False)
            (stage / "labels.json").write_text(json.dumps([{"name": image.stem + suffix, "labels": []}]))
            (stage / "evidence.jsonl").write_text(json.dumps({"image_id": image.stem, "boxes": []}) + "\n")
        else:
            prepare(stage)
            (stage / "ranked_queue_fixture-review-v1.csv").rename(stage / "ranked_queue.csv")
            (stage / "evidence_fixture-review-v1.jsonl").rename(stage / "evidence.jsonl")
            (stage / "yolo_preds.parquet").rename(stage / "predictions.parquet")
        (stage / "demo.env").unlink(missing_ok=True)
        if errors := contracts.check_queue(pd.read_csv(stage / "ranked_queue.csv")):
            raise ValueError("; ".join(errors))
        package_extension(stage / "extension.zip")
        (stage / "credentials.env.example").write_text("CVAT_USER=\nCVAT_PASSWORD=\n")
        manifest = {"identity": identity, "purpose": "development", "real_detector": False,
                    "scored_qc": False,
                    "files": {str(p.relative_to(stage)): sha(p) for p in stage.rglob("*") if p.is_file()}}
        atomic_json(stage / "demo.json", manifest)
        stage.rename(folder)
    environment(folder)
    return manifest


def connect_demo(folder: Path, cvat_url: str, task_name: str, *, client=None) -> dict:
    folder = folder.resolve()
    manifest = verify(folder)
    with tempfile.TemporaryDirectory(dir=folder.parent) as temp:
        mapping = Path(temp) / "mapping.parquet"
        if existing := manifest.get("cvat"):
            if existing["url"] != cvat_url or existing["name"] != task_name:
                raise ValueError("Demo đã gắn CVAT/task khác; không đổi mapping hiện có")
            result = existing
        else:
            if (folder / "cvat_map.parquet").exists() or (folder / "review.db").exists():
                raise ValueError("Đã có mapping/DB chưa được đăng ký; không tạo lại task")
            result = import_batch(cvat_url, folder / "ranked_queue.csv", folder / "images",
                                  folder / "labels.json", task_name, client=client)
            result.update(url=cvat_url)
            # Record task before sync, so failed sync cannot cause another import.
            manifest["cvat"] = result
            atomic_json(folder / "demo.json", manifest)
        expected = pd.read_csv(folder / "ranked_queue.csv").image_id.tolist()
        count = sync(cvat_url, mapping, task_ids=[result["task_id"]], image_ids=expected, client=client)
        if count != len(expected):
            raise ValueError("Mapping thiếu ảnh; task giữ nguyên để kiểm tra, chưa bật demo")
        target = folder / "cvat_map.parquet"
        if target.exists():
            old = pd.read_parquet(target)
            if not old.equals(pd.read_parquet(mapping)):
                raise ValueError("Mapping đã thay đổi; không ghi đè mapping cũ")
        else:
            shutil.copyfile(mapping, target)
    environment(folder, cvat_url)
    return result


def pack_demo(folder: Path, output: Path) -> dict:
    """Export only owned inputs; task IDs, mappings, DB, local env and secrets stay local."""
    folder = folder.resolve()
    manifest = verify(folder)
    if output.exists():
        raise ValueError("Package đã tồn tại; chọn tên mới, không ghi đè")
    portable = {k: v for k, v in manifest.items() if k not in {"cvat", "environment_sha256"}}
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent) as temp:
        archive = Path(temp) / "demo.zip"
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
            for name in portable["files"]:
                if name.endswith((".env", ".db", ".sqlite", ".parquet")) and name != "predictions.parquet":
                    raise ValueError("Không đóng gói credentials, database hoặc mapping")
                bundle.write(folder / name, name)
            bundle.writestr("demo.json", json.dumps(portable, indent=2))
        archive.rename(output)
    return {"package": str(output), "files": len(portable["files"]) + 1,
            "mapping_included": False, "database_included": False, "credentials_included": False}
