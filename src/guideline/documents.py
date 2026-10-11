"""Verify DOCX pagination by rendering a PDF; never infer page numbers from paragraphs."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path


class DocumentError(ValueError):
    pass


def read_document(file: Path, cache_dir: Path) -> dict:
    if file.suffix.lower() not in {".pdf", ".docx"}:
        raise DocumentError("Chỉ đọc DOCX hoặc PDF")
    digest = hashlib.sha256(file.read_bytes()).hexdigest()
    folder = cache_dir / "documents" / digest
    folder.mkdir(parents=True, exist_ok=True)
    pdf = file
    conversion = "original-pdf"
    if file.suffix.lower() == ".docx":
        executable = shutil.which("libreoffice") or shutil.which("soffice")
        if not executable:
            raise DocumentError("DOCX cần LibreOffice để có trang PDF kiểm chứng được")
        version = subprocess.run([executable, "--version"], capture_output=True, text=True, timeout=20)
        conversion = version.stdout.strip()
        pdf = folder / "source.pdf"
        meta = folder / "conversion.json"
        if not (
            pdf.exists() and meta.exists() and json.loads(meta.read_text()).get("converter") == conversion
        ):
            shutil.copyfile(file, folder / "source.docx")
            with tempfile.TemporaryDirectory(prefix="m13-libreoffice-") as profile:
                result = subprocess.run(
                    [
                        executable,
                        f"-env:UserInstallation={Path(profile).as_uri()}",
                        "--headless",
                        "--convert-to",
                        "pdf",
                        "--outdir",
                        str(folder),
                        str(folder / "source.docx"),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=90,
                )
            if result.returncode or not pdf.exists():
                raise DocumentError("LibreOffice không tạo được PDF; kiểm tra cài đặt/font và quyền chạy")
            meta.write_text(json.dumps({"converter": conversion}), encoding="utf-8")
    try:
        import pdfplumber
    except ImportError as exc:
        raise DocumentError("Cài optional dependencies: pip install -e '.[guideline]' ") from exc
    with pdfplumber.open(pdf) as document:
        pages = [{"page": i, "text": page.extract_text() or ""} for i, page in enumerate(document.pages, 1)]
    if not any(page["text"].strip() for page in pages):
        raise DocumentError("PDF không có văn bản đọc được; tài liệu scan cần OCR kiểm chứng riêng")
    result = {
        "file": str(file.resolve()),
        "sha256": digest,
        "pdf_file": str(pdf.resolve()),
        "pdf_sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
        "converter": conversion,
        "pages": pages,
    }
    (folder / "pages.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def quote_problems(spec: dict, pages: list[dict]) -> list[dict]:
    texts = {page["page"]: " ".join(page["text"].split()) for page in pages}
    problems = []
    for section in ("rules", "visual_rules", "facts"):
        for rule in spec.get(section, []):
            quote = " ".join(rule["quote"].split())
            if not quote or quote not in texts.get(rule["page"], ""):
                problems.append(
                    {
                        "section": section,
                        "id": rule.get("id", rule.get("field")),
                        "page": rule["page"],
                        "problem": "quote_not_found",
                    }
                )
    return problems
