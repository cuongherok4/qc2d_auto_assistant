"""Optional real Chromium MV3 + API test. CVAT page is explicitly a fixture."""

import json
import os
import socket
import threading
import time
from pathlib import Path

import pandas as pd
import pytest
from fastapi.responses import HTMLResponse, JSONResponse

pytestmark = pytest.mark.skipif(os.environ.get("M13_BROWSER_TESTS") != "1", reason="set M13_BROWSER_TESTS=1")


def test_mv3_real_api_focus_retry_and_all_verdicts(tmp_path):
    uvicorn = pytest.importorskip("uvicorn")
    browser = pytest.importorskip("playwright.sync_api")
    image_module = pytest.importorskip("PIL.Image")
    from src.api.main import create_app
    from src.api.settings import Settings
    from src.contracts import QUEUE_COLS

    images = tmp_path / "images"
    images.mkdir()
    for i in range(3):
        image_module.new("RGB", (1280, 720), (50, 100, 140)).save(images / f"fixture-{i}.png")
    queue = tmp_path / "ranked_queue_fixture.csv"
    pd.DataFrame(
        [
            [f"fixture-{i}", 90 - i, i + 1, f"[R1] FIXTURE: cao {15 + i}px (tr.1)", "fixture"]
            for i in range(3)
        ],
        columns=QUEUE_COLS,
    ).to_csv(queue, index=False)
    mapping = tmp_path / "map.parquet"
    pd.DataFrame(
        [[f"fixture-{i}", 1, 2, i] for i in range(3)], columns=["image_id", "task_id", "job_id", "frame"]
    ).to_parquet(mapping, index=False)
    evidence = tmp_path / "evidence_fixture.jsonl"
    evidence.write_text(
        "\n".join(
            json.dumps(
                {
                    "image_id": f"fixture-{i}",
                    "boxes": [
                        {
                            "obj_id": str(i),
                            "box": [10, 20, 200, 150],
                            "note": "Fixture box",
                            "signal": "fixture",
                        }
                    ],
                }
            )
            for i in range(3)
        )
    )
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    settings = Settings(
        database=tmp_path / "review.db",
        images=images,
        mapping=mapping,
        predictions=tmp_path / "missing.parquet",
        reports=tmp_path,
        queue_file=queue,
        evidence_file=evidence,
        cvat_url=f"http://127.0.0.1:{port}",
    )
    app = create_app(settings)
    failures = []

    @app.middleware("http")
    async def ambiguous_response(request, call_next):
        response = await call_next(request)
        if request.method == "POST" and request.url.path == "/verdict" and not failures:
            failures.append(True)
            return JSONResponse(
                {"detail": "Fixture: lost acknowledgement AFTER SQLite commit"}, status_code=503
            )
        return response

    @app.get("/tasks/1/jobs/2")
    def cvat_fixture():
        return HTMLResponse("<h1>CVAT PAGE FIXTURE — not real annotation storage</h1>")

    server = uvicorn.Server(uvicorn.Config(app, log_level="error"))
    thread = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.01)
    assert server.started
    try:
        with browser.sync_playwright() as p:
            extension = Path("extension").resolve()
            context = p.chromium.launch_persistent_context(
                str(tmp_path / "chrome"),
                channel="chromium",
                headless=True,
                args=[f"--disable-extensions-except={extension}", f"--load-extension={extension}"],
            )
            worker = (
                context.service_workers[0]
                if context.service_workers
                else context.wait_for_event("serviceworker")
            )
            worker.evaluate(
                "cfg => chrome.storage.local.set({settings: cfg})",
                {
                    "apiUrl": f"http://127.0.0.1:{port}",
                    "reviewer": "Browser fixture reviewer",
                    "batch": "",
                    "sessionId": "fixture-browser",
                    "order": "priority",
                },
            )
            panel = context.new_page()
            errors = []
            panel.on("pageerror", lambda err: errors.append(str(err)))
            panel.goto(worker.url.replace("/background.js", "/sidepanel.html"))
            panel.locator(".row").first.wait_for()
            assert panel.locator(".row").count() == 3
            assert panel.locator(".row strong").first.inner_text() == "[R1]"
            with context.expect_page() as opened:
                panel.locator(".row").first.click()
            cvat = opened.value
            cvat.wait_for_load_state()
            panel.locator("#selected").wait_for(state="visible")
            browser.expect(panel.locator("#boxes")).to_have_attribute("width", "1280")
            assert cvat.url.endswith("/tasks/1/jobs/2?frame=0")
            cvat.bring_to_front()

            def clock():
                return panel.evaluate("chrome.runtime.sendMessage({type:'CLOCK'})")["value"]

            panel.wait_for_timeout(200)
            assert clock()["running"] is True
            # Real CVAT removes ?frame=0 from its URL. The displayed default is still frame zero.
            cvat.evaluate("history.replaceState(null, '', location.pathname)")
            cvat.wait_for_timeout(100)
            assert clock()["running"] is True
            before = clock()["seconds"]
            cvat.wait_for_timeout(150)
            assert clock()["seconds"] > before
            for frame in ("1", "invalid", ""):
                cvat.evaluate("f => history.replaceState(null, '', location.pathname + '?frame=' + f)", frame)
                cvat.wait_for_timeout(50)
                assert clock()["running"] is False
            cvat.evaluate("history.replaceState(null, '', location.pathname + '?frame=0')")
            cvat.wait_for_timeout(50)
            assert clock()["running"] is True
            extra = context.new_page()
            extra.goto("about:blank")
            extra.bring_to_front()
            first = clock()
            assert first["running"] is False
            panel.wait_for_timeout(100)
            assert clock()["seconds"] == first["seconds"]
            panel.bring_to_front()
            panel.locator('[data-verdict="error"]').click()
            panel.locator("#retry").wait_for(state="visible")
            assert len(app.state.store.records()) == 1
            assert panel.locator(".row").count() == 3  # UI has not claimed saved after lost acknowledgement.
            panel.locator("#retry").click()
            browser.expect(panel.locator(".row")).to_have_count(2)
            assert len(app.state.store.records()) == 1
            for key, expected in [("2", "false_alarm"), ("3", "skip")]:
                panel.locator(".row").first.click()
                panel.locator("#selected").wait_for(state="visible")
                panel.keyboard.press(key)
                panel.locator("#selected").wait_for(state="hidden")
                assert app.state.store.records()[-1]["verdict"] == expected
            browser.expect(panel.locator(".row")).to_have_count(0)
            assert len(app.state.store.records()) == 3
            panel.get_by_text("Thống kê phiên", exact=True).click()
            browser.expect(panel.locator("#stats")).to_contain_text("3 ảnh")
            assert not errors
            context.close()
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        sock.close()
