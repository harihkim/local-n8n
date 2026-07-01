from __future__ import annotations

import urllib.error
from email.message import Message

from local_n8n.core import readiness


class FakeResponse:
    def __init__(self, status: int, body: str = "<html>n8n</html>") -> None:
        self.status = status
        self.body = body

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        return None

    def read(self, size: int = -1) -> bytes:
        return self.body.encode()


def test_wait_for_editor_ready_returns_true_on_success(monkeypatch) -> None:
    monkeypatch.setattr(
        "local_n8n.core.readiness.urlopen",
        lambda request, timeout: FakeResponse(200),
    )

    assert readiness.wait_for_editor_ready("http://localhost:5678", timeout_seconds=0.1)


def test_wait_for_editor_ready_retries_until_success(monkeypatch) -> None:
    responses = [
        urllib.error.URLError("connection refused"),
        urllib.error.HTTPError("url", 404, "not ready", Message(), None),
        FakeResponse(200),
    ]

    def fake_urlopen(request, timeout):
        response = responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr("local_n8n.core.readiness.urlopen", fake_urlopen)
    monkeypatch.setattr("local_n8n.core.readiness.time.sleep", lambda seconds: None)

    assert readiness.wait_for_editor_ready(
        "http://localhost:5678",
        timeout_seconds=1,
        interval_seconds=0.01,
    )


def test_wait_for_editor_ready_times_out(monkeypatch) -> None:
    monkeypatch.setattr(
        "local_n8n.core.readiness.urlopen",
        lambda request, timeout: (_ for _ in ()).throw(urllib.error.URLError("nope")),
    )
    monkeypatch.setattr("local_n8n.core.readiness.time.sleep", lambda seconds: None)

    assert not readiness.wait_for_editor_ready(
        "http://localhost:5678",
        timeout_seconds=0,
        interval_seconds=0.01,
    )


def test_editor_readiness_rejects_cannot_get_response(monkeypatch) -> None:
    monkeypatch.setattr(
        "local_n8n.core.readiness.urlopen",
        lambda request, timeout: FakeResponse(200, "Cannot GET /"),
    )

    assert not readiness.is_editor_ready("http://localhost:5678")
