from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from local_n8n.core.diagnostics import debug


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


def _write_stderr(data: bytes) -> None:
    buffer = getattr(sys.stderr, "buffer", None)
    if buffer is not None:
        buffer.write(data)
        buffer.flush()
        return

    sys.stderr.write(data.decode("utf-8", errors="replace"))
    sys.stderr.flush()
