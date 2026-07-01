from __future__ import annotations

import subprocess
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
