"""Real Chromium editor test; approvals apply ONLY to temporary synthetic fixtures."""

import copy
import os
import socket
import threading

import pytest
from test_guideline import SAMPLES, make_pdf

from src.guideline.editor import create_editor
from src.guideline.extract import extract

pytestmark = pytest.mark.skipif(os.environ.get("M13_BROWSER_TESTS") != "1", reason="set M13_BROWSER_TESTS=1")


def test_editor_tables_save_invalid_quote_and_fixture_human_confirmation(tmp_path):
    import uvicorn

    browser = pytest.importorskip("playwright.sync_api")
    source = tmp_path / "source.pdf"
    make_pdf(source, SAMPLES[0]["paragraphs"][1:])
    drafts = tmp_path / "drafts"
    original = extract(source, drafts, options={"cache_dir": str(tmp_path / "cache"),
                       "provider": "fixture", "model": "unit-fixture"},
                       backend=lambda *args: copy.deepcopy(SAMPLES[0]["response"]))
    before = original.read_bytes()
    app = create_editor(drafts, tmp_path / "approved")
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen(5)
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level="error"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    try:
        with browser.sync_playwright() as playwright:
            chromium = playwright.chromium.launch(headless=True)
            page = chromium.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(f"http://127.0.0.1:{port}")
            page.locator("table[data-group=rules]").wait_for()
            assert "chưa duyệt" in page.locator("#approval-status").inner_text()
            page.locator("#reviewer").fill("Automated UNIT FIXTURE approval")
            quote = page.locator("table[data-group=rules] textarea[data-field=quote]").first
            old_quote = quote.input_value()
            quote.fill("invented source quote")
            page.locator("#save").click()
            browser.expect(page.locator("#error")).to_contain_text("quote")
            browser.expect(page.locator("#action-error")).to_contain_text("quote")
            quote.fill(old_quote)
            page.locator("table[data-group=rules] textarea[data-field=message]").first.fill("Fixture revised")
            page.evaluate("""() => {
              const fetchOriginal = window.fetch;
              window.fetchOriginal = fetchOriginal;
              window.saveCalls = 0;
              window.fetch = async (...args) => {
                const saving = String(args[0]).endsWith('/save');
                if (saving) window.saveCalls++;
                const response = await fetchOriginal(...args);
                if (saving) await new Promise(resolve => { window.releaseSave = resolve; });
                return response;
              };
            }""")
            page.locator("#save").click()
            browser.expect(page.locator("#action-feedback")).to_contain_text("Đang kiểm tra và lưu")
            browser.expect(page.locator("#save")).to_be_disabled()
            browser.expect(page.locator("#approve")).to_be_disabled()
            page.evaluate("() => { document.querySelector('#save').onclick(); }")
            page.wait_for_function("() => typeof window.releaseSave === 'function'")
            assert page.evaluate("window.saveCalls") == 1
            page.evaluate("window.releaseSave()")
            browser.expect(page.locator("#status")).to_contain_text("Đã lưu bản nháp mới")
            browser.expect(page.locator("#action-feedback")).to_contain_text("chưa duyệt")
            browser.expect(page.locator("#action-feedback")).to_be_in_viewport()
            browser.expect(page.locator("#save")).to_be_enabled()
            assert original.read_bytes() == before
            page.locator("#approve").click()
            browser.expect(page.locator("#error")).to_contain_text("xác nhận")
            browser.expect(page.locator("#action-error")).to_contain_text("xác nhận")
            page.locator("#confirmed").check()
            page.locator("#approve").click()
            browser.expect(page.locator("#approval-status")).to_contain_text("Đã duyệt bởi")
            browser.expect(page.locator("#action-feedback")).to_contain_text("Đã duyệt bản")
            browser.expect(page.locator("#approve")).to_be_disabled()
            page.locator("table[data-group=rules] textarea[data-field=message]").first.fill(
                "Fixture after approval"
            )
            page.evaluate("window.fetch = window.fetchOriginal")
            page.locator("#save").click()
            browser.expect(page.locator("#status")).to_contain_text("Đã lưu bản nháp mới")
            assert "chưa duyệt" in page.locator("#approval-status").inner_text()
            assert errors == []
            chromium.close()
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        sock.close()
