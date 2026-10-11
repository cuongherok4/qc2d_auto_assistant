"""Bước 0 · LLM đọc guideline DOCX/PDF -> configs/guidelines/drafts/<id>.yaml. Phụ trách: Long.
Hướng dẫn: skill `guideline-rules` mục "Bước LLM đọc guideline".

Temperature 0, validate bằng pydantic, mỗi luật có page + quote nguyên văn, cache theo sha256 file.
Không tự điền ngưỡng thiếu: đưa vào `unclear`. Luôn ghi ra drafts/ với approved_by rỗng.
"""

from __future__ import annotations

from pathlib import Path


def extract(guideline_file: Path, out_dir: Path) -> Path:
    raise NotImplementedError("TODO(Long): đọc guideline bằng LLM, ghi spec nháp")
