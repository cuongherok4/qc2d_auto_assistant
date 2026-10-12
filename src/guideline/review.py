"""A local, escaped review sheet; generating it never approves a guideline."""

from __future__ import annotations

import json
from html import escape
from pathlib import Path

import yaml

from src import config
from src.guideline.documents import read_document
from src.guideline.extract import validate_source


def review_sheet(draft: Path, out: Path) -> Path:
    spec = yaml.safe_load(draft.read_text(encoding="utf-8"))
    source = spec["source"]
    if out.resolve() in {draft.resolve(), Path(source["file"]).resolve(), Path(source["pdf_file"]).resolve()}:
        raise ValueError("Review sheet không được ghi đè draft hoặc tài liệu nguồn")
    try:
        validate_source(spec)
        status = "Schema, hash và quote đạt. Người duyệt vẫn phải kiểm ý nghĩa/mapping check."
    except (ValueError, OSError) as error:
        status = f"Cần xử lý trước khi duyệt: {error}"
    document = read_document(
        Path(source["file"]), config.ROOT / config.load("guideline_extract")["cache_dir"],
        text_options=source.get("text_options", {}), table_options=source.get("table_options", {}),
    )
    def pre(value):
        return "<pre>" + escape(json.dumps(value, ensure_ascii=False, indent=2)) + "</pre>"
    sections = [
        "<!doctype html><html lang='vi'><meta charset='utf-8'>",
        "<meta http-equiv='Content-Security-Policy' "
        "content=\"default-src 'none'; style-src 'unsafe-inline'\">",
        "<title>Đối chiếu guideline</title><style>body{max-width:1100px;margin:24px auto;",
        "padding:16px;font:16px/1.5 sans-serif}pre{white-space:pre-wrap;overflow-wrap:anywhere;",
        "background:#f3f5f7;padding:12px}a{color:#1565c0}</style>",
        "<h1>Đối chiếu guideline</h1><p>Trang này không duyệt spec. ",
        "Chỉ người phụ trách đã đối chiếu PDF mới chạy lệnh approve.</p>",
        "<p>" + escape(status) + "</p>",
        "<p>Trạng thái approved_by: " + escape(spec.get("approved_by") or "chưa duyệt") + "</p>",
        "<p>PDF nguồn: <a href='" + escape(Path(source["pdf_file"]).as_uri(), quote=True)
        + "'>mở PDF</a></p>",
        "<h2>Nguồn và các giá trị trích</h2>" + pre(source),
        pre({key: spec.get(key) for key in (
            "classes", "merge", "min_height_px", "required_attributes", "near_threshold_px", "iou_loose",
        )}),
    ]
    for name in ("rules", "visual_rules", "facts", "unclear"):
        sections.append("<h2>" + escape(name) + "</h2>" + pre(spec.get(name, [])))
    sections.append("<h2>Provenance và sửa bản nháp</h2>" + pre(spec.get("extraction", {})))
    for page in document["pages"]:
        sections.append(
            f"<details><summary>Nguồn trích · trang {page['page']}</summary>"
            + pre(page) + "</details>"
        )
    sections.append("</html>")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(sections), encoding="utf-8")
    return out
