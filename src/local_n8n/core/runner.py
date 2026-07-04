from __future__ import annotations

import errno
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from local_n8n.core.diagnostics import debug


class _PtyUnavailableError(Exception):
    pass


@dataclass(frozen=True)
class CommandResult:
    args: list[str]
    returncode: int
    stdout: str
    stderr: str


def run(args: list[str], cwd: Path) -> CommandResult:
    debug(f"running command: {' '.join(args)} (cwd={cwd})")
    completed = subprocess.run(
        args,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    return CommandResult(
        args=args,
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def run_streaming(args: list[str], cwd: Path) -> CommandResult:
    debug(f"streaming command: {' '.join(args)} (cwd={cwd})")
    if _should_stream_with_tty():
        try:
            return _run_streaming_with_pty(args, cwd)
        except _PtyUnavailableError as exc:
            debug(f"tty streaming unavailable; falling back to plain streaming: {exc}")

    return _run_streaming_plain(args, cwd)


def _run_streaming_plain(args: list[str], cwd: Path) -> CommandResult:
    process = subprocess.Popen(
        args,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    output = bytearray()
    assert process.stdout is not None

    while True:
        chunk = os.read(process.stdout.fileno(), 8192)
        if not chunk:
            break
        output.extend(chunk)
        _write_stderr(chunk)

    returncode = process.wait()
    combined = output.decode("utf-8", errors="replace")
    return CommandResult(
        args=args,
        returncode=returncode,
        stdout="",
        stderr=combined,
    )


def _run_streaming_with_pty(args: list[str], cwd: Path) -> CommandResult:
    try:
        import pty

        master_fd, slave_fd = pty.openpty()
    except (ImportError, OSError) as exc:
        raise _PtyUnavailableError(str(exc)) from exc

    try:
        try:
            process = subprocess.Popen(
                args,
                cwd=cwd,
                stdin=subprocess.DEVNULL,
                stdout=slave_fd,
                stderr=slave_fd,
                close_fds=True,
            )
        except BaseException:
            os.close(master_fd)
            raise
    finally:
        os.close(slave_fd)

    output = bytearray()
    try:
        while True:
            try:
                chunk = os.read(master_fd, 8192)
            except OSError as exc:
                if exc.errno == errno.EIO:
                    break
                raise
            if not chunk:
                break
            output.extend(chunk)
            _write_stderr(chunk)
    finally:
        os.close(master_fd)

    returncode = process.wait()
    combined = output.decode("utf-8", errors="replace")
    return CommandResult(
        args=args,
        returncode=returncode,
        stdout="",
        stderr=combined,
    )


def _should_stream_with_tty() -> bool:
    isatty = getattr(sys.stderr, "isatty", None)
    if isatty is None:
        return False
    try:
        return bool(isatty())
    except OSError:
        return False


def _write_stderr(data: bytes) -> None:
    buffer = getattr(sys.stderr, "buffer", None)
    if buffer is not None:
        buffer.write(data)
        buffer.flush()
        return

    sys.stderr.write(data.decode("utf-8", errors="replace"))
    sys.stderr.flush()
