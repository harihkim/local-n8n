from __future__ import annotations

import json
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
        _docker_backend_check(),
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
            hint=_docker_missing_hint(),
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
            hint=_docker_missing_hint(),
            exit_code=10,
        )
    if result.returncode != 0:
        return DoctorCheck(
            name="Docker daemon",
            ok=False,
            detail="not reachable",
            hint=_docker_unreachable_hint(),
            exit_code=10,
        )
    return DoctorCheck(name="Docker daemon", ok=True, detail="reachable")


def _docker_backend_check() -> DoctorCheck:
    try:
        result = run(["docker", "info", "--format", "{{json .}}"], cwd=Path.cwd())
    except FileNotFoundError:
        return DoctorCheck(name="Docker backend", ok=True, detail="skipped; docker not found")
    if result.returncode != 0:
        return DoctorCheck(
            name="Docker backend",
            ok=True,
            detail="skipped; Docker daemon not reachable",
        )

    info = _load_docker_info(result.stdout)
    backend_detail = _docker_backend_detail(info)
    if _looks_like_docker_desktop(info):
        context = _docker_context()
        detail = backend_detail
        if context:
            detail = f"{detail}; context={context}"
        if platform.system() == "Windows":
            hint = "Docker Desktop for Windows is active."
        elif _is_wsl():
            hint = (
                "Docker Desktop WSL integration is active. Docker resources are managed by "
                "Docker Desktop's WSL backend."
            )
        else:
            hint = "Docker Desktop is active."
        return DoctorCheck(
            name="Docker backend",
            ok=True,
            detail=detail,
            hint=hint,
        )

    return DoctorCheck(name="Docker backend", ok=True, detail=backend_detail)


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


def _load_docker_info(raw_output: str) -> dict[str, object]:
    try:
        parsed = json.loads(raw_output)
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    return parsed


def _docker_backend_detail(info: dict[str, object]) -> str:
    operating_system = _string_value(info.get("OperatingSystem"))
    name = _string_value(info.get("Name"))
    if operating_system and name:
        return f"{operating_system}; name={name}"
    return operating_system or name or "unknown Docker backend"


def _looks_like_docker_desktop(info: dict[str, object]) -> bool:
    values = [
        _string_value(info.get("OperatingSystem")),
        _string_value(info.get("Name")),
    ]
    return any(
        "docker desktop" in value.lower() or "docker-desktop" in value.lower() for value in values
    )


def _docker_context() -> str | None:
    try:
        result = run(["docker", "context", "show"], cwd=Path.cwd())
    except FileNotFoundError:
        return None
    if result.returncode != 0:
        return None
    context = result.stdout.strip()
    return context or None


def _string_value(value: object) -> str:
    return value if isinstance(value, str) else ""


def _docker_missing_hint() -> str:
    if platform.system() == "Windows":
        return "Install Docker Desktop for Windows, start it, then re-run doctor."
    if platform.system() == "Darwin":
        return "Install Docker Desktop for Mac or Colima, then re-run doctor."
    if _is_wsl():
        return (
            "Install Docker Desktop for Windows and enable WSL integration for this distro, "
            "or install Docker Engine directly inside WSL."
        )
    return "Install Docker Engine or Docker Desktop, then re-run doctor."


def _docker_unreachable_hint() -> str:
    if platform.system() == "Windows":
        return "Start Docker Desktop for Windows, then re-run doctor."
    if platform.system() == "Darwin":
        return "Start Docker Desktop for Mac or Colima, then re-run doctor."
    if _is_wsl():
        return (
            "Start Docker Desktop and enable WSL integration for this distro, or start "
            "Docker Engine inside WSL."
        )
    return "Start Docker Engine or Docker Desktop, then re-run doctor."


def _is_wsl() -> bool:
    osrelease = Path("/proc/sys/kernel/osrelease")
    if not osrelease.exists():
        return False
    try:
        return "microsoft" in osrelease.read_text(encoding="utf-8").lower()
    except OSError:
        return False
