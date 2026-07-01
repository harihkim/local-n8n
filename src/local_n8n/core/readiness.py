from __future__ import annotations

import time
from http import HTTPStatus
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from local_n8n.core.diagnostics import debug

READY_MARKERS = ("n8n", "window.base_path", "/assets/")
NOT_READY_MARKERS = ("cannot get", "cannot post")


def wait_for_editor_ready(
    url: str,
    timeout_seconds: float = 90.0,
    interval_seconds: float = 2.0,
) -> bool:
    deadline = time.monotonic() + timeout_seconds

    while time.monotonic() < deadline:
        debug(f"checking editor readiness: {url}")
        if is_editor_ready(url):
            return True
        time.sleep(interval_seconds)

    return False


def is_editor_ready(url: str) -> bool:
    request = Request(url, headers={"User-Agent": "lon-readiness/0.1"})
    try:
        with urlopen(request, timeout=5) as response:
            if not HTTPStatus.OK <= response.status < HTTPStatus.BAD_REQUEST:
                return False
            body = response.read(65536).decode("utf-8", errors="ignore").lower()
            return _looks_like_editor(body)
    except HTTPError as exc:
        debug(f"editor readiness HTTP error: {exc.code}")
        return False
    except (ConnectionError, TimeoutError, URLError, OSError):
        return False


def _looks_like_editor(body: str) -> bool:
    if not body:
        return False
    if any(marker in body for marker in NOT_READY_MARKERS):
        return False
    return any(marker in body for marker in READY_MARKERS)
