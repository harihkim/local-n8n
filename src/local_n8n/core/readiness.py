from __future__ import annotations

import time
from http import HTTPStatus
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from local_n8n.core.diagnostics import debug

READY_MARKERS = ("n8n", "window.base_path", "/assets/")
READY_PATHS = ("/setup",)
NOT_READY_MARKERS = (
    "cannot get",
    "cannot post",
    "n8n is starting up",
    "please wait",
)


def wait_for_web_ui_ready(
    url: str,
    timeout_seconds: float = 90.0,
    interval_seconds: float = 2.0,
) -> bool:
    deadline = time.monotonic() + timeout_seconds

    while time.monotonic() < deadline:
        debug(f"checking n8n web UI readiness: {url}")
        if is_web_ui_ready(url):
            return True
        time.sleep(interval_seconds)

    return False


def is_web_ui_ready(url: str) -> bool:
    request = Request(url, headers={"User-Agent": "lon-readiness/0.1"})
    try:
        with urlopen(request, timeout=5) as response:
            if not HTTPStatus.OK <= response.status < HTTPStatus.BAD_REQUEST:
                return False
            body = response.read(65536).decode("utf-8", errors="ignore").lower()
            return _looks_like_web_ui(body, response.geturl())
    except HTTPError as exc:
        debug(f"n8n web UI readiness HTTP error: {exc.code}")
        return False
    except (ConnectionError, TimeoutError, URLError, OSError):
        return False


def _looks_like_web_ui(body: str, final_url: str = "") -> bool:
    if not body:
        return False
    if any(marker in body for marker in NOT_READY_MARKERS):
        return False
    if urlparse(final_url).path in READY_PATHS and "n8n" in body:
        return True
    return any(marker in body for marker in READY_MARKERS)
