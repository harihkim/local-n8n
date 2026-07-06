from __future__ import annotations

from local_n8n.bootstrap.docker import plan_docker_bootstrap
from local_n8n.core.doctor import DoctorCheck, DoctorReport


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
