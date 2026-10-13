"""Local guideline editor: immutable revisions, checked citations, explicit human approval."""

from __future__ import annotations

import copy
import hashlib
import json
import secrets
import threading
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import yaml
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, StrictBool
from starlette.middleware.trustedhost import TrustedHostMiddleware

from src.guideline.extract import approve, atomic_yaml, validate_source
from src.guideline.schema import ExtractedSpec

WEB = Path(__file__).with_name("web")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Edit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: str
    reviewer: str = Field(min_length=1, max_length=100)
    content: dict


class Approval(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: str
    reviewer: str = Field(min_length=1, max_length=100)
    confirmed: StrictBool = False


class Drafts:
    def __init__(self, drafts: Path, approved: Path):
        self.drafts, self.approved = drafts.resolve(), approved.resolve()
        if not self.drafts.is_dir() or self.drafts.name != "drafts":
            raise ValueError("Chọn thư mục drafts hiện có")
        if self.approved == self.drafts or self.approved.is_relative_to(self.drafts):
            raise ValueError("Thư mục approved phải nằm ngoài drafts")
        self.files: dict[str, Path] = {}
        self.lock = threading.Lock()
        self.refresh()

    def refresh(self):
        files = {}
        for root in (self.drafts, self.approved):
            for path in root.rglob("*.yaml"):
                if path.is_symlink() or not path.resolve().is_relative_to(root):
                    continue
                key = hashlib.sha256(str(path.resolve()).encode()).hexdigest()[:24]
                files[key] = path
        self.files = files

    def path(self, key):
        path = self.files.get(key)
        if path is None or path.is_symlink() or not path.is_file():
            raise HTTPException(404, "Không có draft đã đăng ký")
        return path

    def detail(self, key):
        path = self.path(key)
        spec = yaml.safe_load(path.read_text())
        try:
            validate_source(spec)
            problems = []
        except (ValueError, OSError) as error:
            problems = [str(error)]
        return {"key": key, "filename": path.name, "revision": digest(path), "spec": spec,
                "problems": problems, "approved": bool(spec.get("approved_by"))}

    def check_revision(self, key, revision):
        path = self.path(key)
        if digest(path) != revision:
            raise HTTPException(409, "File đã thay đổi; tải lại trước khi lưu/duyệt")
        return path, yaml.safe_load(path.read_text())

    def save(self, key, value: Edit):
        with self.lock:
            path, old = self.check_revision(key, value.revision)
            if set(value.content) - set(ExtractedSpec.model_fields):
                raise ValueError("Không sửa source, approved_by, extraction hoặc chính sách severity")
            raw = ExtractedSpec.model_validate(value.content).model_dump(exclude_none=True)
            if raw["id"] != old["id"] or raw["version"] != old["version"]:
                raise ValueError("ID/version được giữ bởi hệ thống; phiên sửa sẽ tăng patch version")
            reviewer = value.reviewer.strip()
            if not reviewer:
                raise ValueError("Cần tên người chỉnh sửa")
            spec = {**copy.deepcopy(old), **raw, "approved_by": ""}
            # Rule severity belongs to the existing shared policy, not an editor input.
            from src import config

            policy = config.load("guideline_extract")["rule_severity"]
            for rule in spec["rules"]:
                rule["severity"] = policy[rule["check"]]
            validate_source(spec)
            versions = []
            for registered in self.files.values():
                other = yaml.safe_load(registered.read_text())
                if other.get("id") == spec["id"]:
                    versions.append(tuple(map(int, other["version"].split("."))))
            current = tuple(map(int, old["version"].split(".")))
            latest = max([current, *versions])
            spec["version"] = f"{latest[0]}.{latest[1]}.{latest[2] + 1}"
            extraction = spec.setdefault("extraction", {})
            extraction["quote_problems"] = []
            entry = {"editor": reviewer, "at": datetime.now(UTC).isoformat(),
                     "parent_sha256": digest(path), "parent_filename": path.name,
                     "content_sha256": hashlib.sha256(json.dumps(raw, sort_keys=True).encode()).hexdigest(),
                     "approved": False}
            extraction.setdefault("review_history", []).append(entry)
            extraction.setdefault("draft_corrections", []).append(entry)
            target = self.drafts / f"{spec['id']}@{spec['version']}-{uuid4().hex[:12]}.yaml"
            atomic_yaml(target, spec)
            self.refresh()
            new_key = next(k for k, p in self.files.items() if p == target)
            return self.detail(new_key)

    def human_approve(self, key, value: Approval):
        with self.lock:
            path, spec = self.check_revision(key, value.revision)
            if spec.get("approved_by"):
                raise ValueError("Bản này đã duyệt; sửa sẽ tạo draft mới")
            target = approve(path, value.reviewer, acknowledged=value.confirmed,
                             outdir=self.approved / spec["id"] / spec["version"])
            self.refresh()
            return self.detail(next(k for k, p in self.files.items() if p == target))


def create_editor(drafts: Path, approved: Path, *, token: str | None = None) -> FastAPI:
    repo = Drafts(drafts, approved)
    token = token or secrets.token_urlsafe(32)
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.state.repo, app.state.token = repo, token
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1"])

    @app.middleware("http")
    async def protect(request: Request, call_next):
        from fastapi.responses import JSONResponse

        if request.url.path.startswith("/api/") or request.url.path.startswith("/source/"):
            supplied = request.headers.get("X-M13-Token", "")
            if not secrets.compare_digest(supplied, token):
                return JSONResponse({"detail": "Thiếu phiên duyệt local hợp lệ"}, status_code=403)
            origin = request.headers.get("origin")
            if origin and origin != str(request.base_url).rstrip("/"):
                return JSONResponse({"detail": "Origin không hợp lệ"}, status_code=403)
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'"
        )
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.get("/")
    def index():
        return FileResponse(WEB / "index.html")

    @app.get("/editor.js")
    def script():
        return FileResponse(WEB / "editor.js")

    @app.get("/editor.css")
    def style():
        return FileResponse(WEB / "editor.css")

    @app.get("/session")
    def session(request: Request):
        # A foreign browser origin cannot read this response (no CORS); block
        # cross-site fetch explicitly as well. Token never enters URLs or logs.
        if request.headers.get("sec-fetch-site") == "cross-site":
            raise HTTPException(403, "Mở giao diện trực tiếp trên localhost")
        origin = request.headers.get("origin")
        if origin and origin != str(request.base_url).rstrip("/"):
            raise HTTPException(403, "Origin không hợp lệ")
        return {"token": token}

    @app.get("/api/drafts")
    def listing():
        repo.refresh()
        keys = sorted(repo.files, key=lambda key: repo.files[key].stat().st_mtime_ns, reverse=True)
        return [{k: v for k, v in repo.detail(key).items() if k != "spec"} for key in keys]

    @app.get("/api/drafts/{key}")
    def detail(key: str):
        return repo.detail(key)

    @app.get("/source/{key}")
    def source(key: str):
        spec = repo.detail(key)["spec"]
        try:
            validate_source(spec)
        except (ValueError, OSError) as error:
            raise HTTPException(422, str(error)) from None
        return FileResponse(spec["source"]["pdf_file"], media_type="application/pdf")

    def action(fn, key, value):
        try:
            return fn(key, value)
        except (ValueError, OSError) as error:
            raise HTTPException(422, str(error)) from None

    @app.post("/api/drafts/{key}/save")
    def save(key: str, value: Edit):
        return action(repo.save, key, value)

    @app.post("/api/drafts/{key}/approve")
    def approval(key: str, value: Approval):
        return action(repo.human_approve, key, value)

    return app
