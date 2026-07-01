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
