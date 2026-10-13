import copy
import json
from pathlib import Path

import httpx
import pytest
import yaml
from pydantic import ValidationError

pytest.importorskip("pdfplumber")

from src import config
from src.guideline.documents import DocumentError, quote_problems, read_document
from src.guideline.extract import ApprovalError, approve, extract, load_approved
from src.guideline.provider import ProviderError, gemini
from src.guideline.schema import ExtractedSpec

SAMPLES = json.loads((Path(__file__).parent / "fixtures/guidelines/samples.json").read_text())


def make_pdf(path, lines, *, stream=None):
    """Small original text PDF; no OCR or external tools needed for unit tests."""
    escaped = [line.replace("(", "\\(").replace(")", "\\)") for line in lines]
    stream = stream or (
        "BT /F1 10 Tf 40 700 Td " + " ".join(f"({line}) Tj 0 -20 Td" for line in escaped) + " ET"
    )
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream".encode(),
    ]
    data, offsets = b"%PDF-1.4\n", [0]
    for i, obj in enumerate(objects, 1):
        offsets.append(len(data))
        data += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(data)
    data += b"xref\n0 6\n0000000000 65535 f \n" + b"".join(
        f"{offset:010d} 00000 n \n".encode() for offset in offsets[1:]
    )
    data += f"trailer << /Size 6 /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    path.write_bytes(data)


@pytest.fixture
def sample(tmp_path):
    file = tmp_path / "source.pdf"
    make_pdf(file, SAMPLES[0]["paragraphs"][1:])
    return file, {"cache_dir": str(tmp_path / "cache"), "provider": "fixture", "model": "unit-fixture"}


def test_extract_schema_quotes_cache_and_unapproved(sample, tmp_path):
    file, options = sample
    calls = []

    def backend(pages, schema, cfg):
        calls.append(pages)
        assert "properties" in schema and cfg["temperature"] == 0
        return copy.deepcopy(SAMPLES[0]["response"])

    path = extract(file, tmp_path / "drafts", options=options, backend=backend)
    spec = yaml.safe_load(path.read_text())
    assert spec["approved_by"] == "" and not spec["extraction"]["quote_problems"]
    assert spec["min_height_px"] == {"car": 15}
    assert "default" not in spec["min_height_px"]
    assert any(u["category"] == "truck" for u in spec["unclear"])
    assert spec["rules"][0]["severity"] == 0.6  # Explicit risk policy, not an LLM threshold.
    with pytest.raises(ApprovalError, match="chưa có người duyệt"):
        load_approved(path)
    extract(file, tmp_path / "drafts", options=options, backend=backend)
    assert len(calls) == 1
    extract(file, tmp_path / "drafts", options={**options, "model": "another-fixture"}, backend=backend)
    assert len(calls) == 2
    make_pdf(file, [*SAMPLES[0]["paragraphs"][1:], "Source changed."])
    extract(file, tmp_path / "drafts", options=options, backend=backend)
    assert len(calls) == 3


def test_small_font_pdf_word_gaps_and_quote_verification(tmp_path):
    import pdfplumber

    source = tmp_path / "tight-words.pdf"
    make_pdf(source, [], stream="BT /F1 10 Tf 40 700 Td [(Box) -200 (car)] TJ ET")
    with pdfplumber.open(source) as document:
        assert document.pages[0].extract_text() == "Boxcar"
    document = read_document(source, tmp_path / "cache", text_options={"x_tolerance_ratio": 0.15})
    assert document["pages"][0]["text"] == "Box car"
    assert not quote_problems(
        {"facts": [{"field": "classes", "page": 1, "quote": "Box car"}]}, document["pages"]
    )
    assert quote_problems(
        {"facts": [{"field": "classes", "page": 1, "quote": "Box truck"}]}, document["pages"]
    )


def test_cache_changes_when_extracted_pages_change(sample, tmp_path, monkeypatch):
    import src.guideline.extract as module

    file, options = sample
    calls = []
    def backend(*args):
        calls.append(True)
        return copy.deepcopy(SAMPLES[0]["response"])
    path = extract(file, tmp_path / "drafts", options=options, backend=backend)
    previous = yaml.safe_load(path.read_text())["extraction"]["cache_id"]
    original = module.read_document
    def changed(*args, **kwargs):
        document = original(*args, **kwargs)
        document["pages_sha256"] = "a different extractor's text hash"
        return document
    monkeypatch.setattr(module, "read_document", changed)
    extract(file, tmp_path / "drafts", options=options, backend=backend)
    assert len(calls) == 2
    assert yaml.safe_load(path.read_text())["extraction"]["cache_id"] != previous


def test_table_citation_stays_on_its_page_and_in_one_cell():
    pages = [
        {"page": 1, "text": "Table columns interleaved", "tables": [[["car, truck", "bus"]]]},
        {"page": 2, "text": "Another page"},
    ]
    fact = {"field": "classes", "page": 1, "quote": "car, truck"}
    assert not quote_problems({"facts": [fact]}, pages)
    assert quote_problems({"facts": [{**fact, "page": 2}]}, pages)
    assert quote_problems({"facts": [{**fact, "quote": "car, truck bus"}]}, pages)


def test_extract_preserves_valid_draft_corrections(sample, tmp_path):
    file, options = sample
    path = extract(file, tmp_path / "drafts", options=options, backend=lambda *args: SAMPLES[0]["response"])
    spec = yaml.safe_load(path.read_text())
    spec["rules"][0]["message"] = "Reviewer sửa cách diễn đạt"
    spec["extraction"]["draft_corrections"] = [{"rule_id": "R1", "reason": "sửa bản nháp"}]
    path.write_text(yaml.safe_dump(spec, allow_unicode=True))
    before = path.read_bytes()
    def forbidden(*args):
        raise AssertionError("Valid cache must avoid the backend")
    assert extract(file, tmp_path / "drafts", options=options, backend=forbidden).read_bytes() == before


def test_review_sheet_escapes_content_and_keeps_draft_unapproved(sample, tmp_path):
    from src.guideline.review import review_sheet

    file, options = sample
    path = extract(file, tmp_path / "drafts", options=options, backend=lambda *args: SAMPLES[0]["response"])
    spec = yaml.safe_load(path.read_text())
    spec["rules"][0]["message"] = "<script>alert('source injection')</script>"
    path.write_text(yaml.safe_dump(spec))
    before = path.read_bytes()
    output = review_sheet(path, tmp_path / "review.html")
    text = output.read_text()
    assert "<script>" not in text and "&lt;script&gt;" in text
    assert "chưa duyệt" in text and "Nguồn trích" in text
    assert path.read_bytes() == before and yaml.safe_load(path.read_text())["approved_by"] == ""
    with pytest.raises(ValueError, match="ghi đè"):
        review_sheet(path, file)


def test_invalid_quote_blocks_approval(sample, tmp_path):
    file, options = sample
    response = copy.deepcopy(SAMPLES[0]["response"])
    response["rules"][0]["quote"] = "This text was hallucinated."
    path = extract(file, tmp_path / "drafts", options=options, backend=lambda *args: response)
    spec = yaml.safe_load(path.read_text())
    assert spec["extraction"]["quote_problems"][0]["problem"] == "quote_not_found"
    with pytest.raises(ApprovalError, match="quote"):
        approve(path, "Fixture reviewer", acknowledged=True, outdir=tmp_path / "approved")


def test_missing_citation_or_invented_threshold_fails_schema(sample, tmp_path):
    file, options = sample
    bad = copy.deepcopy(SAMPLES[0]["response"])
    bad["min_height_px"]["car"] = 900
    with pytest.raises(ValidationError, match="không xuất hiện"):
        extract(file, tmp_path / "drafts", options=options, backend=lambda *args: bad)
    assert not list((tmp_path / "cache/responses").glob("*.json"))
    bad = copy.deepcopy(SAMPLES[0]["response"])
    bad["facts"] = []
    with pytest.raises(ValidationError, match="Thiếu citation"):
        ExtractedSpec.model_validate(bad)


def test_approval_requires_confirmation_and_original_source(sample, tmp_path, monkeypatch):
    file, options = sample
    path = extract(file, tmp_path / "drafts", options=options, backend=lambda *args: SAMPLES[0]["response"])
    with pytest.raises(ApprovalError, match="confirm-reviewed"):
        approve(path, "Fixture reviewer", acknowledged=False, outdir=tmp_path / "approved")
    # Isolate all approval caches as well as extraction caches.
    original_load = config.load
    monkeypatch.setattr(
        config,
        "load",
        lambda name: (
            {**original_load(name), **options} if name == "guideline_extract" else original_load(name)
        ),
    )
    approved = approve(path, "Fixture reviewer", acknowledged=True, outdir=tmp_path / "approved")
    assert load_approved(approved)["approved_by"] == "Fixture reviewer"
    file.write_bytes(file.read_bytes() + b"\nChanged")
    with pytest.raises(ApprovalError, match="Nguồn đã đổi"):
        approve(path, "Fixture reviewer", acknowledged=True, outdir=tmp_path / "approved")


def test_page_numbers_and_empty_source(tmp_path):
    file = tmp_path / "source.pdf"
    make_pdf(file, ["Allowed classes: car, truck."])
    document = read_document(file, tmp_path / "cache")
    assert document["pages"][0]["page"] == 1
    assert quote_problems(
        {"rules": [{"page": 2, "quote": "Allowed classes: car, truck.", "id": "R1"}]}, document["pages"]
    )
    make_pdf(file, [])
    with pytest.raises(DocumentError, match="không có văn bản"):
        read_document(file, tmp_path / "cache")


def test_loading_approved_rechecks_schema_quote_and_source(sample, tmp_path, monkeypatch):
    file, options = sample
    path = extract(file, tmp_path / "drafts", options=options, backend=lambda *args: SAMPLES[0]["response"])
    original_load = config.load
    monkeypatch.setattr(config, "load", lambda name: {**original_load(name), **options})
    approved = approve(path, "Fixture reviewer", acknowledged=True, outdir=tmp_path / "approved")
    spec = yaml.safe_load(approved.read_text())
    spec["rules"][0]["quote"] = "Not in the source."
    approved.write_text(yaml.safe_dump(spec))
    with pytest.raises(ApprovalError, match="quote"):
        load_approved(approved)
    spec["rules"][0]["quote"] = SAMPLES[0]["response"]["rules"][0]["quote"]
    approved.write_text(yaml.safe_dump(spec))
    file.write_bytes(file.read_bytes() + b"\nChanged after approval")
    with pytest.raises(ApprovalError, match="Nguồn đã đổi"):
        load_approved(approved)


@pytest.mark.parametrize("schema_mode", ["responseFormat", "responseJsonSchema"])
def test_gemini_rest_schema_temperature_and_key_sanitization(monkeypatch, schema_mode):
    monkeypatch.setenv("GEMINI_API_KEY", "unit-secret-value")
    cfg = config.load("guideline_extract")
    cfg["schema_mode"] = schema_mode
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "finishReason": "STOP",
                        "content": {"parts": [{"text": json.dumps(SAMPLES[0]["response"])}]},
                    }
                ]
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = gemini(
            [{"page": 1, "text": "Sample"}], ExtractedSpec.model_json_schema(), cfg, client=client
        )
    body = json.loads(seen[0].content)
    assert body["generationConfig"]["temperature"] == 0
    assert schema_mode in body["generationConfig"]
    if schema_mode == "responseFormat":
        assert body["generationConfig"]["responseFormat"]["text"]["mimeType"] == "APPLICATION_JSON"
    else:
        assert body["generationConfig"]["responseMimeType"] == "application/json"
    assert seen[0].headers["x-goog-api-key"] == "unit-secret-value"
    assert "unit-secret-value" not in str(seen[0].url)
    assert result["id"] == SAMPLES[0]["id"]
    with httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(429, text="unit-secret-value"))
    ) as client:
        with pytest.raises(ProviderError, match="HTTP 429") as error:
            gemini([], {}, cfg, client=client)
    assert "unit-secret-value" not in str(error.value)
    monkeypatch.delenv("GEMINI_API_KEY")
    with pytest.raises(ProviderError, match="Thiếu biến"):
        gemini([], {}, cfg)
