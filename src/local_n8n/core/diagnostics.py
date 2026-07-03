from __future__ import annotations

import sys

_VERBOSE = False


def set_verbose(value: bool) -> None:
    global _VERBOSE
    _VERBOSE = value


def verbose_enabled() -> bool:
    return _VERBOSE


def debug(message: str) -> None:
    if _VERBOSE:
        print(f"debug: {message}", file=sys.stderr)
