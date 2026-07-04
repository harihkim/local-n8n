from __future__ import annotations

from pathlib import Path

import pytest

from local_n8n.core.doctor import DoctorCheck, run_doctor
from local_n8n.core.runner import CommandResult


def test_doctor_passes_when_prereqs_are_available(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("local_n8n.core.doctor.shutil.which", lambda name: "/usr/bin/docker")
    monkeypatch.setattr(
        "local_n8n.core.doctor._port_check",
        lambda port: DoctorCheck("Port 0", True, "available"),
    )

    def fake_run(args: list[str], cwd: Path) -> CommandResult:
        stdout = "Docker Compose version v5.1.4" if args == ["docker", "compose", "version"] else ""
        return CommandResult(args=args, returncode=0, stdout=stdout, stderr="")

    monkeypatch.setattr("local_n8n.core.doctor.run", fake_run)

    report = run_doctor(port=0)

    assert report.ok
    assert report.exit_code == 0


def test_doctor_reports_missing_docker(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("local_n8n.core.doctor.shutil.which", lambda name: None)
    monkeypatch.setattr(
        "local_n8n.core.doctor._port_check",
        lambda port: DoctorCheck("Port 0", True, "available"),
    )

    def fake_run(args: list[str], cwd: Path) -> CommandResult:
        raise FileNotFoundError("docker")

    monkeypatch.setattr("local_n8n.core.doctor.run", fake_run)

    report = run_doctor(port=0)

    assert not report.ok
    assert report.exit_code == 10
    assert any(check.name == "Docker CLI" and not check.ok for check in report.checks)


def test_doctor_passes_wsl_engine_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("local_n8n.core.doctor._is_wsl", lambda: True)
    monkeypatch.setattr("local_n8n.core.doctor.shutil.which", lambda name: "/usr/bin/docker")
    monkeypatch.setattr(
        "local_n8n.core.doctor._port_check",
        lambda port: DoctorCheck("Port 0", True, "available"),
    )

    def fake_run(args: list[str], cwd: Path) -> CommandResult:
        if args == ["docker", "info", "--format", "{{json .}}"]:
            return CommandResult(
                args=args,
                returncode=0,
                stdout='{"OperatingSystem":"Ubuntu 24.04","Name":"wsl-engine"}',
                stderr="",
            )
        if args == ["docker", "compose", "version"]:
            return CommandResult(
                args=args, returncode=0, stdout="Docker Compose version v5.1.4", stderr=""
            )
        return CommandResult(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr("local_n8n.core.doctor.run", fake_run)

    report = run_doctor(port=0)

    assert report.ok
    backend = next(check for check in report.checks if check.name == "Docker backend")
    assert backend.detail == "Ubuntu 24.04; name=wsl-engine"


def test_doctor_accepts_docker_desktop_wsl_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("local_n8n.core.doctor._is_wsl", lambda: True)
    monkeypatch.setattr("local_n8n.core.doctor.shutil.which", lambda name: "/usr/bin/docker")
    monkeypatch.setattr(
        "local_n8n.core.doctor._port_check",
        lambda port: DoctorCheck("Port 0", True, "available"),
    )

    def fake_run(args: list[str], cwd: Path) -> CommandResult:
        if args == ["docker", "info", "--format", "{{json .}}"]:
            return CommandResult(
                args=args,
                returncode=0,
                stdout='{"OperatingSystem":"Docker Desktop","Name":"docker-desktop"}',
                stderr="",
            )
        if args == ["docker", "context", "show"]:
            return CommandResult(args=args, returncode=0, stdout="desktop-linux\n", stderr="")
        if args == ["docker", "compose", "version"]:
            return CommandResult(
                args=args, returncode=0, stdout="Docker Compose version v5.1.4", stderr=""
            )
        return CommandResult(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr("local_n8n.core.doctor.run", fake_run)

    report = run_doctor(port=0)

    assert report.ok
    assert report.exit_code == 0
    backend = next(check for check in report.checks if check.name == "Docker backend")
    assert backend.ok
    assert backend.detail == "Docker Desktop; name=docker-desktop; context=desktop-linux"
    assert backend.hint is not None
    assert "Docker Desktop WSL integration is active" in backend.hint


def test_doctor_guides_wsl_when_docker_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("local_n8n.core.doctor._is_wsl", lambda: True)
    monkeypatch.setattr("local_n8n.core.doctor.shutil.which", lambda name: None)
    monkeypatch.setattr(
        "local_n8n.core.doctor._port_check",
        lambda port: DoctorCheck("Port 0", True, "available"),
    )

    def fake_run(args: list[str], cwd: Path) -> CommandResult:
        raise FileNotFoundError("docker")

    monkeypatch.setattr("local_n8n.core.doctor.run", fake_run)

    report = run_doctor(port=0)

    assert not report.ok
    cli = next(check for check in report.checks if check.name == "Docker CLI")
    assert cli.hint is not None
    assert "enable WSL integration" in cli.hint
    assert "Docker Engine directly inside WSL" in cli.hint


def test_doctor_guides_wsl_when_docker_daemon_is_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("local_n8n.core.doctor._is_wsl", lambda: True)
    monkeypatch.setattr("local_n8n.core.doctor.shutil.which", lambda name: "/usr/bin/docker")
    monkeypatch.setattr(
        "local_n8n.core.doctor._port_check",
        lambda port: DoctorCheck("Port 0", True, "available"),
    )

    def fake_run(args: list[str], cwd: Path) -> CommandResult:
        if args == ["docker", "compose", "version"]:
            return CommandResult(
                args=args, returncode=0, stdout="Docker Compose version v5.1.4", stderr=""
            )
        return CommandResult(args=args, returncode=1, stdout="", stderr="daemon unavailable")

    monkeypatch.setattr("local_n8n.core.doctor.run", fake_run)

    report = run_doctor(port=0)

    assert not report.ok
    daemon = next(check for check in report.checks if check.name == "Docker daemon")
    assert daemon.hint is not None
    assert "Start Docker Desktop" in daemon.hint
    assert "enable WSL integration" in daemon.hint
