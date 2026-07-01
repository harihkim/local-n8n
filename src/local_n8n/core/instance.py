from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from local_n8n.compose.template import ensure_instance_files
from local_n8n.core.config import build_instance_config
from local_n8n.core.errors import (
    CommandFailedError,
    PortInUseError,
    PrerequisiteError,
)
from local_n8n.core.runner import CommandResult, run


@dataclass(frozen=True)
class UpResult:
    url: str
    compose_path: Path
    volume_name: str


@dataclass(frozen=True)
class DownResult:
    volume_name: str


def up_instance(instance_name: str, port: int = 5678) -> UpResult:
    config = build_instance_config(instance_name, port)
    ensure_instance_files(config)

    _run_compose(
        config.instance_dir,
        [
            "docker",
            "compose",
            "-p",
            config.project_name,
            "-f",
            str(config.compose_path),
            "up",
            "-d",
        ],
    )
    return UpResult(
        url=f"http://localhost:{port}",
        compose_path=config.compose_path,
        volume_name=config.volume_name,
    )


def down_instance(instance_name: str) -> DownResult:
    config = build_instance_config(instance_name)
    _run_compose(
        config.instance_dir,
        [
            "docker",
            "compose",
            "-p",
            config.project_name,
            "-f",
            str(config.compose_path),
            "down",
        ],
    )
    return DownResult(volume_name=config.volume_name)


def _run_compose(cwd: Path, command: list[str]) -> CommandResult:
    try:
        result = run(command, cwd=cwd)
    except FileNotFoundError as exc:
        raise PrerequisiteError(
            "Docker was not found.",
            hint="Install Docker Engine inside WSL/Linux, then re-run this command.",
        ) from exc

    if result.returncode == 0:
        return result

    stderr = result.stderr.lower()
    stdout = result.stdout.lower()
    output = f"{stderr}\n{stdout}"

    if "cannot connect to the docker daemon" in output or "docker daemon is not running" in output:
        raise PrerequisiteError(
            "Docker is installed, but the daemon is not running.",
            hint="Start Docker Engine in WSL/Linux, then re-run this command.",
        )

    if (
        "port is already allocated" in output
        or "address already in use" in output
        or "ports are not available" in output
    ):
        raise PortInUseError(
            "Port 5678 is already in use.",
            hint="Stop the process using the port, or run with a different --port.",
        )

    raise CommandFailedError(
        "Docker Compose failed.",
        hint=(
            result.stderr.strip()
            or result.stdout.strip()
            or "Run again with Docker output available."
        ),
    )
