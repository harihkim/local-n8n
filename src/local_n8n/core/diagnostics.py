from __future__ import annotations

import os
import sys
from datetime import UTC, datetime
from pathlib import Path

_VERBOSE = False
_LOG_PATH: Path | None = None


def set_verbose(value: bool) -> None:
    global _VERBOSE
    _VERBOSE = value


def verbose_enabled() -> bool:
    return _VERBOSE


def start_log(config_home: Path, argv: list[str] | None = None) -> Path | None:
    global _LOG_PATH

    logs_dir = config_home / "logs"
    try:
        logs_dir.mkdir(parents=True, exist_ok=True)
        timestamp = _timestamp_for_filename()
        path = _unused_log_path(logs_dir, timestamp)
        path.touch(mode=0o600, exist_ok=False)
    except OSError as exc:
        _LOG_PATH = None
        if _VERBOSE:
            print(f"debug: diagnostic log unavailable: {exc}", file=sys.stderr)
        return None

    _LOG_PATH = path
    info(f"diagnostic log started: {path}")
    if argv is not None:
        info(f"argv: {_redact_argv(argv)}")
    return path


def log_path() -> Path | None:
    return _LOG_PATH


def debug(message: str) -> None:
    _write("debug", message)
    if _VERBOSE:
        print(f"debug: {message}", file=sys.stderr)


def info(message: str) -> None:
    _write("info", message)


def error(message: str) -> None:
    _write("error", message)


def _write(level: str, message: str) -> None:
    if _LOG_PATH is None:
        return

    timestamp = datetime.now(UTC).isoformat(timespec="seconds")
    with _LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(f"{timestamp} {level}: {message}\n")


def _timestamp_for_filename() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _unused_log_path(logs_dir: Path, timestamp: str) -> Path:
    base_name = f"lon-{timestamp}-{os.getpid()}"
    path = logs_dir / f"{base_name}.log"
    index = 1
    while path.exists():
        path = logs_dir / f"{base_name}-{index}.log"
        index += 1
    return path


def _redact_argv(argv: list[str]) -> str:
    redacted: list[str] = []
    redact_next = False
    for value in argv:
        if redact_next:
            redacted.append("<redacted>")
            redact_next = False
            continue
        redacted.append(value)
        if value in {"--password", "--passphrase", "--recovery-code", "--secret"}:
            redact_next = True
    return " ".join(redacted)
