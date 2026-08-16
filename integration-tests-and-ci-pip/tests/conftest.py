import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from unittest.mock import MagicMock

import pytest
import requests


class _MockHandler(BaseHTTPRequestHandler):
    """Captures POST bodies for Slack/PagerDuty webhook stubs."""
    received = []

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b""
        try:
            parsed = json.loads(body)
        except Exception:
            parsed = body.decode()
        _MockHandler.received.append({"path": self.path, "body": parsed})
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"ok":true}')

    def log_message(self, *_):
        pass


@pytest.fixture(autouse=True)
def _clear_received():
    _MockHandler.received.clear()
    yield
    _MockHandler.received.clear()


@pytest.fixture(scope="session")
def mock_webhook_server():
    """Start a local HTTP server that captures webhook calls."""
    server = HTTPServer(("127.0.0.1", 0), _MockHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield port
    server.shutdown()


@pytest.fixture()
def webhook_calls():
    return _MockHandler.received


@pytest.fixture()
def api_client():
    """Return a requests session pointed at the rules engine API."""
    base = "http://127.0.0.1:8000"
    s = requests.Session()
    s.base_url = base
    s.get_rule = lambda rid: s.get(f"{base}/rules/{rid}")
    s.list_rules = lambda: s.get(f"{base}/rules")
    s.create_rule = lambda data: s.post(f"{base}/rules", json=data)
    s.update_rule = lambda rid, data: s.put(f"{base}/rules/{rid}", json=data)
    s.delete_rule = lambda rid: s.delete(f"{base}/rules/{rid}")
    s.ingest_metric = lambda data: s.post(f"{base}/metrics", json=data)
    s.alerts = lambda: s.get(f"{base}/alerts")
    return s