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

    docker_cli = failed.get("Docker CLI")
    if docker_cli is not None:
        actions.append(
            BootstrapAction(
                name="install-docker",
                reason="Docker CLI is not installed.",
                commands=[],
                manual_hint=docker_cli.hint or "Install Docker Engine or Docker Desktop.",
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


def _report(progress: ProgressReporter | None, message: str) -> None:
    if progress is not None:
        progress(message)
