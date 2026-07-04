from __future__ import annotations

import platform
import shutil
import socket
from dataclasses import dataclass
from pathlib import Path

from local_n8n.core.runner import run


@dataclass(frozen=True)
class DoctorCheck:
    name: str
    ok: bool
    detail: str
    hint: str | None = None
    exit_code: int = 1


@dataclass(frozen=True)
class DoctorReport:
    checks: list[DoctorCheck]

    @property
    def ok(self) -> bool:
        return all(check.ok for check in self.checks)

    @property
    def exit_code(self) -> int:
        for check in self.checks:
            if not check.ok:
                return check.exit_code
        return 0


def run_doctor(port: int = 5678, check_port: bool = True) -> DoctorReport:
    checks = [
        _platform_check(),
        _docker_cli_check(),
        _docker_daemon_check(),
        _docker_compose_check(),
    ]
    if check_port:
        checks.append(_port_check(port))
    return DoctorReport(checks=checks)


def _platform_check() -> DoctorCheck:
    system = platform.system()
    detail = system
    if system == "Linux" and _is_wsl():
        detail = "Linux (WSL)"
    return DoctorCheck(name="Platform", ok=True, detail=detail)


def _docker_cli_check() -> DoctorCheck:
    docker_path = shutil.which("docker")
    if docker_path is None:
        return DoctorCheck(
            name="Docker CLI",
            ok=False,
            detail="not found",
            hint="Install Docker Engine inside WSL/Linux, then re-run doctor.",
            exit_code=10,
        )
    return DoctorCheck(name="Docker CLI", ok=True, detail=docker_path)


def _docker_daemon_check() -> DoctorCheck:
    try:
        result = run(["docker", "info"], cwd=Path.cwd())
    except FileNotFoundError:
        return DoctorCheck(
            name="Docker daemon",
            ok=False,
            detail="docker command not found",
            hint="Install Docker Engine inside WSL/Linux, then re-run doctor.",
            exit_code=10,
        )
    if result.returncode != 0:
        return DoctorCheck(
            name="Docker daemon",
            ok=False,
            detail="not reachable",
            hint="Start Docker Engine, then re-run doctor.",
            exit_code=10,
        )
    return DoctorCheck(name="Docker daemon", ok=True, detail="reachable")


def _docker_compose_check() -> DoctorCheck:
    try:
        result = run(["docker", "compose", "version"], cwd=Path.cwd())
    except FileNotFoundError:
        return DoctorCheck(
            name="Docker Compose",
            ok=False,
            detail="docker command not found",
            hint="Install Docker Engine with the Compose plugin.",
            exit_code=10,
        )
    if result.returncode != 0:
        return DoctorCheck(
            name="Docker Compose",
            ok=False,
            detail="not available",
            hint="Install or repair the Docker Compose plugin.",
            exit_code=10,
        )
    return DoctorCheck(name="Docker Compose", ok=True, detail=result.stdout.strip() or "available")


def _port_check(port: int) -> DoctorCheck:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            return DoctorCheck(
                name=f"Port {port}",
                ok=False,
                detail="in use",
                hint=f"Stop the process using port {port}, or choose another --port.",
                exit_code=11,
            )
    return DoctorCheck(name=f"Port {port}", ok=True, detail="available")


def _is_wsl() -> bool:
    osrelease = Path("/proc/sys/kernel/osrelease")
    if not osrelease.exists():
        return False
    try:
        return "microsoft" in osrelease.read_text(encoding="utf-8").lower()
    except OSError:
        return False
