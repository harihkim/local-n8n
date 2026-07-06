from __future__ import annotations

from dataclasses import dataclass

from local_n8n.core.doctor import DoctorReport


@dataclass(frozen=True)
class BootstrapAction:
    name: str
    reason: str
    command: list[str] | None
    manual_hint: str


@dataclass(frozen=True)
class BootstrapPlan:
    actions: list[BootstrapAction]

    @property
    def needed(self) -> bool:
        return bool(self.actions)


def plan_docker_bootstrap(report: DoctorReport) -> BootstrapPlan:
    actions: list[BootstrapAction] = []
    failed = {check.name: check for check in report.checks if not check.ok}

    docker_cli = failed.get("Docker CLI")
    if docker_cli is not None:
        actions.append(
            BootstrapAction(
                name="install-docker",
                reason="Docker CLI is not installed.",
                command=None,
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
                command=None,
                manual_hint=docker_daemon.hint or "Start Docker Engine or Docker Desktop.",
            )
        )

    docker_compose = failed.get("Docker Compose")
    if docker_compose is not None:
        actions.append(
            BootstrapAction(
                name="install-compose-plugin",
                reason="Docker Compose plugin is missing or not available.",
                command=None,
                manual_hint=docker_compose.hint or "Install or repair the Docker Compose plugin.",
            )
        )

    return BootstrapPlan(actions=actions)
