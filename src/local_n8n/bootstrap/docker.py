from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from local_n8n.core.doctor import DoctorReport
from local_n8n.core.errors import CommandFailedError
from local_n8n.core.runner import CommandResult, run_streaming

ProgressReporter = Callable[[str], None]
CommandRunner = Callable[[list[str], Path], CommandResult]


@dataclass(frozen=True)
class BootstrapAction:
    name: str
    reason: str
    commands: list[list[str]]
    manual_hint: str

    @property
    def executable(self) -> bool:
        return bool(self.commands)


@dataclass(frozen=True)
class BootstrapPlan:
    actions: list[BootstrapAction]

    @property
    def needed(self) -> bool:
        return bool(self.actions)


@dataclass(frozen=True)
class BootstrapActionResult:
    action: BootstrapAction
    ran_commands: list[list[str]]


def plan_docker_bootstrap(report: DoctorReport) -> BootstrapPlan:
    actions: list[BootstrapAction] = []
    failed = {check.name: check for check in report.checks if not check.ok}
    linux_like = _linux_like(report)
    apt_distro = _supported_apt_distro() if linux_like else None

    docker_cli = failed.get("Docker CLI")
    if docker_cli is not None:
        commands = _docker_engine_install_commands(apt_distro) if apt_distro else []
        actions.append(
            BootstrapAction(
                name="install-docker",
                reason="Docker CLI is not installed.",
                commands=commands,
                manual_hint=(
                    "Install Docker Engine from Docker's official apt repository. "
                    "After installation, open a new shell if Docker group membership changed."
                    if commands
                    else docker_cli.hint or "Install Docker Engine or Docker Desktop."
                ),
            )
        )
        return BootstrapPlan(actions=actions)

    docker_daemon = failed.get("Docker daemon")
    if docker_daemon is not None:
        actions.append(
            BootstrapAction(
                name="start-docker",
                reason="Docker is installed, but the daemon is not reachable.",
                commands=[["sudo", "service", "docker", "start"]] if linux_like else [],
                manual_hint=docker_daemon.hint or "Start Docker Engine or Docker Desktop.",
            )
        )

    docker_compose = failed.get("Docker Compose")
    if docker_compose is not None:
        actions.append(
            BootstrapAction(
                name="install-compose-plugin",
                reason="Docker Compose plugin is missing or not available.",
                commands=[["sudo", "apt-get", "install", "-y", "docker-compose-plugin"]]
                if linux_like
                else [],
                manual_hint=docker_compose.hint or "Install or repair the Docker Compose plugin.",
            )
        )

    return BootstrapPlan(actions=actions)


def apply_bootstrap_plan(
    plan: BootstrapPlan,
    *,
    progress: ProgressReporter | None = None,
    runner: CommandRunner | None = None,
) -> list[BootstrapActionResult]:
    active_runner = runner or run_streaming
    results: list[BootstrapActionResult] = []
    for action in plan.actions:
        if not action.executable:
            _report(progress, f"Manual prerequisite fix needed: {action.manual_hint}")
            continue

        ran_commands: list[list[str]] = []
        for command in action.commands:
            _report(progress, f"Running prerequisite fix: {' '.join(command)}")
            result = active_runner(command, Path.cwd())
            ran_commands.append(command)
            if result.returncode != 0:
                raise CommandFailedError(
                    f"Prerequisite fix failed: {action.name}.",
                    hint=result.stderr.strip() or action.manual_hint,
                    exit_code=10,
                )
        results.append(BootstrapActionResult(action=action, ran_commands=ran_commands))
    return results


def _linux_like(report: DoctorReport) -> bool:
    platform_check = next((check for check in report.checks if check.name == "Platform"), None)
    if platform_check is None:
        return False
    return platform_check.detail.startswith("Linux")


def _supported_apt_distro() -> str | None:
    os_release = _read_os_release(Path("/etc/os-release"))
    distro_id = os_release.get("ID", "").lower()
    id_like = os_release.get("ID_LIKE", "").lower().split()

    if distro_id in {"ubuntu", "debian"}:
        return distro_id
    if "ubuntu" in id_like:
        return "ubuntu"
    if "debian" in id_like:
        return "debian"
    return None


def _read_os_release(path: Path) -> dict[str, str]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}

    values: dict[str, str] = {}
    for line in lines:
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        values[key] = raw_value.strip().strip('"')
    return values


def _docker_engine_install_commands(apt_distro: str | None) -> list[list[str]]:
    if apt_distro not in {"ubuntu", "debian"}:
        return []

    source_script = (
        "set -eu; "
        ". /etc/os-release; "
        'codename="${UBUNTU_CODENAME:-${VERSION_CODENAME:-}}"; '
        'arch="$(dpkg --print-architecture)"; '
        'if [ -z "$codename" ]; then '
        'echo "Unable to determine distribution codename." >&2; exit 1; '
        "fi; "
        "printf '%s\\n' "
        "'Types: deb' "
        f"'URIs: https://download.docker.com/linux/{apt_distro}' "
        '"Suites: $codename" '
        "'Components: stable' "
        '"Architectures: $arch" '
        "'Signed-By: /etc/apt/keyrings/docker.asc' "
        "> /etc/apt/sources.list.d/docker.sources"
    )
    start_script = (
        "set -eu; "
        "if command -v systemctl >/dev/null 2>&1 && systemctl is-system-running >/dev/null 2>&1; "
        "then systemctl start docker; "
        "else service docker start; "
        "fi"
    )
    group_script = (
        "set -eu; "
        'if [ -n "${SUDO_USER:-}" ] && getent group docker >/dev/null 2>&1; '
        'then usermod -aG docker "$SUDO_USER"; '
        "fi"
    )

    return [
        ["sudo", "apt-get", "update"],
        ["sudo", "apt-get", "install", "-y", "ca-certificates", "curl"],
        ["sudo", "install", "-m", "0755", "-d", "/etc/apt/keyrings"],
        [
            "sudo",
            "curl",
            "-fsSL",
            f"https://download.docker.com/linux/{apt_distro}/gpg",
            "-o",
            "/etc/apt/keyrings/docker.asc",
        ],
        ["sudo", "chmod", "a+r", "/etc/apt/keyrings/docker.asc"],
        ["sudo", "sh", "-c", source_script],
        ["sudo", "apt-get", "update"],
        [
            "sudo",
            "apt-get",
            "install",
            "-y",
            "docker-ce",
            "docker-ce-cli",
            "containerd.io",
            "docker-buildx-plugin",
            "docker-compose-plugin",
        ],
        ["sudo", "sh", "-c", start_script],
        ["sudo", "sh", "-c", group_script],
    ]


def _report(progress: ProgressReporter | None, message: str) -> None:
    if progress is not None:
        progress(message)
