"""Prepare a pinned, project-isolated CVAT installation without changing Docker."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import socket
import tempfile
from pathlib import Path

import yaml

from src import config


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def restore_source(out: Path) -> dict:
    """Restore missing bind-mount files only. Never overwrite a file or nonempty directory."""
    source = config.ROOT / config.load("cvat-install")["source_dir"]
    provenance = json.loads((source.parent / "provenance.json").read_text())
    targets = []
    for name, digest in provenance["files"].items():
        original, target = source / name, out / name
        if sha(original) != digest:
            raise ValueError("Source phục hồi đổi hash")
        if target.is_symlink() or any(p.is_symlink() for p in target.parents):
            raise ValueError("Không phục hồi qua symlink")
        if target.exists():
            if target.is_file() and sha(target) == digest:
                continue
            if not target.is_dir() or any(target.iterdir()):
                raise ValueError(f"Đích có nội dung khác; không ghi đè: {name}")
        targets.append((original, target))
    for original, target in targets:
        if target.is_dir():
            target.rmdir()  # Only empty placeholders left by Docker's missing bind source.
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as file:
            file.write(original.read_bytes())
    return {"source": str(out.resolve()), "restored_files": len(targets),
            "containers_changed": False, "files": provenance["files"]}


def preflight(out: Path) -> dict:
    cfg = config.load("cvat-install")
    manifest = json.loads((out / "install.json").read_text())
    for name, digest in manifest["files"].items():
        if sha(out / name) != digest:
            raise ValueError("Bộ cài đã sửa; kiểm lại trước khi chạy")
    memory = None
    if Path("/proc/meminfo").is_file():
        lines = Path("/proc/meminfo").read_text().splitlines()
        available = next(line for line in lines if line.startswith("MemAvailable:"))
        memory = round(int(available.split()[1]) / 1024**2, 2)
    disk = round(shutil.disk_usage(out).free / 1024**3, 2)
    with socket.socket() as probe:
        port_free = probe.connect_ex(("127.0.0.1", manifest["identity"]["port"])) != 0
    return {"available_memory_gib": memory, "free_disk_gib": disk, "port_free": port_free,
            "minimum_available_memory_gib": cfg["min_available_memory_gib"],
            "minimum_free_disk_gib": cfg["min_free_disk_gib"],
            "resources_allow_fresh_start": memory is not None and memory >= cfg["min_available_memory_gib"]
            and disk >= cfg["min_free_disk_gib"] and port_free,
            "fresh_start_verified": False}


def prepare_install(out: Path, *, project: str | None = None, port: int | None = None) -> dict:
    cfg = config.load("cvat-install")
    project, port = project or cfg["project"], port or cfg["port"]
    if not re.fullmatch(r"[a-z][a-z0-9_-]{2,50}", project) or project in {"cvat", "m13_qc2d"}:
        raise ValueError("Chọn project mới, không dùng cvat hoặc m13_qc2d đang phục vụ")
    if not 1024 <= port <= 65535 or port == 8080:
        raise ValueError("Chọn cổng riêng 1024–65535, khác cổng demo 8080")
    source = config.ROOT / cfg["source_dir"]
    provenance = json.loads((source.parent / "provenance.json").read_text())
    for name, digest in provenance["files"].items():
        if sha(source / name) != digest:
            raise ValueError(f"Source CVAT đổi hash: {name}")
    identity = {"version": cfg["version"], "project": project, "port": port, "source": provenance["files"]}
    out = out.resolve()
    manifest = out / "install.json"
    if out.exists():
        if not manifest.is_file():
            raise ValueError("Thư mục đích đã tồn tại; chọn thư mục mới, không ghi đè")
        saved = json.loads(manifest.read_text())
        if saved["identity"] != identity:
            raise ValueError("Bộ cài đã có cấu hình khác; dùng thư mục mới")
        for name, digest in saved["files"].items():
            if sha(out / name) != digest:
                raise ValueError(f"Bộ cài đã sửa: {name}; giữ nguyên, dùng thư mục mới")
        return saved
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=out.parent) as temp:
        stage = Path(temp) / "install"
        shutil.copytree(source, stage)
        compose = yaml.safe_load((stage / "docker-compose.yml").read_text())
        compose["name"] = project
        for service in compose["services"].values():
            service.pop("container_name", None)
            service.setdefault("labels", {})["m13.stack"] = project
            if "NUMPROCS" in service.get("environment", {}):
                service["environment"]["NUMPROCS"] = 1
            if service.get("image", "").startswith(("cvat/server:", "cvat/ui:")):
                service["image"] = service["image"].split(":")[0] + ":" + cfg["version"]
            for key, value in service.get("labels", {}).items():
                if isinstance(value, str):
                    service["labels"][key] = value.replace("${CVAT_HOST:-localhost}", cfg["host"])
            for key, value in service.get("environment", {}).items():
                if isinstance(value, str):
                    service["environment"][key] = value.replace("${CVAT_HOST:-localhost}", cfg["host"])
        router = compose["services"]["traefik"]
        router["ports"] = [f"127.0.0.1:{port}:8080"]
        router["environment"]["TRAEFIK_PROVIDERS_DOCKER_NETWORK"] = f"{project}_cvat"
        router["environment"]["TRAEFIK_PROVIDERS_DOCKER_CONSTRAINTS"] = f"Label(`m13.stack`, `{project}`)"
        # The deleted original source no longer contains dashboard JSON. Core CVAT
        # works independently; do not claim a recovered analytics dashboard.
        grafana = compose["services"]["cvat_grafana"]
        grafana["environment"].pop("GF_DASHBOARDS_DEFAULT_HOME_DASHBOARD_PATH", None)
        grafana["volumes"] = []
        (stage / "docker-compose.yml").write_text(yaml.safe_dump(compose, sort_keys=False))
        result = {"identity": identity, "fresh_start_verified": False,
                  "analytics_dashboard_restored": False,
                  "files": {str(p.relative_to(stage)): sha(p) for p in stage.rglob("*") if p.is_file()}}
        (stage / "install.json").write_text(json.dumps(result, indent=2))
        stage.rename(out)
    return result
