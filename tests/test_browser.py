"""Optional real Chromium integration checks: OKTO_BROWSER_TESTS=1 pytest."""

import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from okto.web import inspect

pytestmark = pytest.mark.skipif(
    os.environ.get("OKTO_BROWSER_TESTS") != "1", reason="requires installed Playwright and Chromium"
)


@pytest.fixture
def server():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/":
                status = 200
                body = b"""<!doctype html><button id="go">Go</button><p style="display:none">clue</p>
<script>
document.querySelector('#go').addEventListener('click', () => {
  console.error('synthetic click error');
  fetch('/failure');
  fetch('/abort').catch(() => {});
  setTimeout(() => { throw new Error('synthetic runtime exception'); }, 10);
});
</script>"""
            elif self.path == "/abort":
                self.connection.close()
                return
            else:
                status = 500 if self.path == "/failure" else 404
                body = b"<p>synthetic error page</p>"
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_):
            pass

    instance = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=instance.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{instance.server_port}"
    finally:
        instance.shutdown()
        instance.server_close()
        thread.join(timeout=2)


def test_runtime_click_network_and_hidden(server):
    report = inspect(server, browser=True, click=["#go"])
    assert report.facts["mode"] == "browser", report.warnings
    runtime = report.facts["runtime"]
    assert any("synthetic click error" in e for e in runtime["errors"])
    assert any("synthetic runtime exception" in e for e in runtime["errors"])
    assert any(e["status"] == 500 for e in runtime["http_errors"])
    assert any("/abort" in e["url"] for e in runtime["failed_requests"])
    assert any(e["text"] == "clue" for e in runtime["hidden_elements"])


def test_http_error_body_is_retained(server):
    report = inspect(server + "/missing")
    assert report.facts["http_status"] == 404
    assert any("HTTP 404" in c.value for c in report.candidates)


def test_incomplete_action_retains_evidence(server):
    report = inspect(server, browser=True, click=["#absent"], timeout=0.3)
    assert report.facts["mode"] == "browser"
    assert any("incomplete" in warning for warning in report.warnings)
