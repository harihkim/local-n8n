from __future__ import annotations

import time
from http import HTTPStatus
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def wait_for_http_ready(
    url: str,
    timeout_seconds: float = 90.0,
    interval_seconds: float = 2.0,
) -> bool:
    deadline = time.monotonic() + timeout_seconds

    while time.monotonic() < deadline:
        if _is_http_ready(url):
            return True
        time.sleep(interval_seconds)

    return False


def _is_http_ready(url: str) -> bool:
    request = Request(url, headers={"User-Agent": "lon-readiness/0.1"})
    try:
        with urlopen(request, timeout=5) as response:
            return HTTPStatus.OK <= response.status < HTTPStatus.BAD_REQUEST
    except HTTPError as exc:
        return HTTPStatus.OK <= exc.code < HTTPStatus.BAD_REQUEST
    except (ConnectionError, TimeoutError, URLError, OSError):
        return False
