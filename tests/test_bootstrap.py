from __future__ import annotations

from pathlib import Path

from local_n8n.bootstrap.docker import apply_bootstrap_plan, plan_docker_bootstrap
from local_n8n.core.doctor import DoctorCheck, DoctorReport
from local_n8n.core.runner import CommandResult


def test_docker_bootstrap_plan_installs_docker_when_cli_is_missing() -> None:
    report = DoctorReport(
        checks=[
            DoctorCheck("Docker CLI", False, "not found", hint="Install Docker.", exit_code=10),
            DoctorCheck("Docker daemon", False, "docker command not found", exit_code=10),
        ]
    )

    plan = plan_docker_bootstrap(report)

    assert plan.needed
    assert [action.name for action in plan.actions] == ["install-docker"]
    assert plan.actions[0].manual_hint == "Install Docker."


def test_docker_bootstrap_plan_starts_daemon_and_installs_compose() -> None:
    report = DoctorReport(
        checks=[
            DoctorCheck("Platform", True, "Linux (WSL)"),
            DoctorCheck("Docker CLI", True, "/usr/bin/docker"),
            DoctorCheck("Docker daemon", False, "not reachable", exit_code=10),
            DoctorCheck("Docker Compose", False, "not available", exit_code=10),
        ]
    )

    plan = plan_docker_bootstrap(report)

    assert [action.name for action in plan.actions] == [
        "start-docker",
        "install-compose-plugin",
    ]
    assert plan.actions[0].commands == [["sudo", "service", "docker", "start"]]
    assert plan.actions[1].commands == [
        ["sudo", "apt-get", "install", "-y", "docker-compose-plugin"]
    ]


def test_docker_bootstrap_plan_noops_when_prereqs_pass() -> None:
    report = DoctorReport(
        checks=[
            DoctorCheck("Docker CLI", True, "/usr/bin/docker"),
            DoctorCheck("Docker daemon", True, "reachable"),
            DoctorCheck("Docker Compose", True, "available"),
        ]
    )

    plan = plan_docker_bootstrap(report)

    assert not plan.needed
    assert plan.actions == []


def test_apply_bootstrap_plan_runs_executable_actions() -> None:
    report = DoctorReport(
        checks=[
            DoctorCheck("Platform", True, "Linux"),
            DoctorCheck("Docker CLI", True, "/usr/bin/docker"),
            DoctorCheck("Docker daemon", False, "not reachable", exit_code=10),
        ]
    )
    plan = plan_docker_bootstrap(report)
    commands: list[list[str]] = []

    def fake_runner(args: list[str], cwd: Path) -> CommandResult:
        commands.append(args)
        return CommandResult(args=args, returncode=0, stdout="", stderr="")

    results = apply_bootstrap_plan(plan, runner=fake_runner)

    assert commands == [["sudo", "service", "docker", "start"]]
    assert results[0].ran_commands == commands
