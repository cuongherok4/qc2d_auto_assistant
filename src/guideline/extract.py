"""Extract a cited draft with validated cache; human approval is a separate CLI action."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from uuid import uuid4

import yaml

from src import config
from src.guideline.documents import quote_problems, read_document
from src.guideline.provider import PROMPT, gemini
from src.guideline.schema import ExtractedSpec


class ApprovalError(ValueError):
    pass


def atomic_yaml(path: Path, spec: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temp.write_text(yaml.safe_dump(spec, allow_unicode=True, sort_keys=False), encoding="utf-8")
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def extract(file: Path, outdir: Path | None = None, *, options: dict | None = None, backend=None) -> Path:
    cfg = {**config.load("guideline_extract"), **(options or {})}
    cache = config.ROOT / cfg["cache_dir"]
    document = read_document(file, cache)
    schema = ExtractedSpec.model_json_schema()
    identity = {
        "source": document["sha256"],
        "pdf": document["pdf_sha256"],
        "converter": document["converter"],
        "schema": schema,
        "prompt": PROMPT,
        "config": {
            k: v
            for k, v in cfg.items()
            if k not in {"cache_dir", "drafts_dir", "approved_dir", "api_key_env"}
        },
    }
    cache_id = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    response_path = cache / "responses" / f"{cache_id}.json"
    cache_hit = response_path.exists()
    if cache_hit:
        result = json.loads(response_path.read_text(encoding="utf-8"))
    else:
        result = (backend or gemini)(document["pages"], schema, cfg)
    validated = ExtractedSpec.model_validate(result)
    spec = validated.model_dump(exclude_none=True)
    problems = quote_problems(spec, document["pages"])
    # Valid structured output is cached even when citations need a human correction.
    # Validation runs again on cache hits; invalid schema is never cached.
    if not cache_hit:
        response_path.parent.mkdir(parents=True, exist_ok=True)
        response_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
    for category in spec["classes"]:
        if "default" not in spec["min_height_px"] and category not in spec["min_height_px"]:
            missing = {"category": category, "field": "min_height_px", "note": "Nguồn chưa ghi ngưỡng"}
            if not any(
                item.get("category") == category and item["field"] == "min_height_px"
                for item in spec["unclear"]
            ):
                spec["unclear"].append(missing)
    for rule in spec["rules"]:
        rule["severity"] = cfg["rule_severity"][rule["check"]]
    spec.update(
        approved_by="",
        source={k: document[k] for k in ("file", "sha256", "pdf_file", "pdf_sha256", "converter")},
        extraction={
            "provider": cfg["provider"],
            "model": cfg["model"],
            "cache_id": cache_id,
            "quote_problems": problems,
            "rule_severity_origin": "configs/guideline_extract.yaml",
        },
    )
    destination = outdir or config.ROOT / cfg["drafts_dir"]
    if destination.name != "drafts":
        raise ValueError(
            "Extract chỉ ghi vào thư mục tên drafts; dùng guideline approve để xuất spec đã duyệt"
        )
    output = destination / f"{spec['id']}@{spec['version']}-{document['sha256'][:8]}.yaml"
    if output.exists() and yaml.safe_load(output.read_text()).get("approved_by"):
        raise ValueError("Không ghi đè spec đã có người duyệt")
    atomic_yaml(output, spec)
    return output


def load_approved(path: Path) -> dict:
    spec = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not str(spec.get("approved_by", "")).strip():
        raise ApprovalError("Spec chưa có người duyệt thực sự")
    if spec.get("extraction", {}).get("quote_problems"):
        raise ApprovalError("Spec còn quote không kiểm chứng được")
    return spec


def approve(draft: Path, reviewer: str, *, acknowledged: bool, outdir: Path | None = None) -> Path:
    if not acknowledged or not reviewer.strip():
        raise ApprovalError("Người duyệt phải đọc PDF/spec và xác nhận --confirm-reviewed")
    spec = yaml.safe_load(draft.read_text(encoding="utf-8"))
    source = spec.get("source", {})
    file = Path(source.get("file", ""))
    if not file.is_file() or hashlib.sha256(file.read_bytes()).hexdigest() != source.get("sha256"):
        raise ApprovalError("Nguồn đã đổi/không còn; trích lại trước khi duyệt")
    document = read_document(file, config.ROOT / config.load("guideline_extract")["cache_dir"])
    if document["pdf_sha256"] != source.get("pdf_sha256"):
        raise ApprovalError("Bản PDF kiểm chứng đã đổi; trích lại")
    raw = {k: spec[k] for k in ExtractedSpec.model_fields if k in spec}
    raw["rules"] = [{k: v for k, v in rule.items() if k != "severity"} for rule in raw.get("rules", [])]
    ExtractedSpec.model_validate(raw)
    problems = quote_problems(raw, document["pages"])
    if problems:
        raise ApprovalError(f"Không duyệt được: quote không tồn tại trong nguồn: {problems}")
    spec["extraction"]["quote_problems"] = []
    spec["approved_by"] = reviewer.strip()
    destination = outdir or config.ROOT / config.load("guideline_extract")["approved_dir"]
    if destination.name == "drafts":
        raise ApprovalError("Spec đã duyệt phải nằm ngoài drafts")
    output = destination / f"{spec['id']}.yaml"
    if output.exists() and yaml.safe_load(output.read_text()) != spec:
        raise ApprovalError("Spec đã tồn tại; tăng version/đổi ID trước khi ghi, không ghi đè lịch sử")
    atomic_yaml(output, spec)
    return output
