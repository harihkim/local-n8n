from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from local_n8n.app import app
from local_n8n.core.doctor import DoctorCheck
from local_n8n.core.runner import CommandResult

runner = CliRunner()


def test_cli_up_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))

    def fake_run(args: list[str], cwd: Path) -> CommandResult:
        return CommandResult(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr("local_n8n.core.instance.run", fake_run)
    monkeypatch.setattr("local_n8n.core.instance.wait_for_http_ready", lambda url: True)

    result = runner.invoke(app, ["up"])

    assert result.exit_code == 0
    assert "Starting n8n and waiting for the editor" in result.stderr
    assert "n8n is running" in result.stderr


def test_cli_up_friendly_error_without_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))

    def fake_run(args: list[str], cwd: Path) -> CommandResult:
        raise FileNotFoundError("docker")

    monkeypatch.setattr("local_n8n.core.instance.run", fake_run)
    monkeypatch.setattr("local_n8n.core.instance.wait_for_http_ready", lambda url: True)

    result = runner.invoke(app, ["up"])

    assert result.exit_code == 10
    assert "Docker was not found" in result.stderr
    assert "Traceback" not in result.stderr


def test_cli_down_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))
    instance_dir = tmp_path / "instances" / "default"
    instance_dir.mkdir(parents=True)
    (instance_dir / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")

    def fake_run(args: list[str], cwd: Path) -> CommandResult:
        return CommandResult(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr("local_n8n.core.instance.run", fake_run)

    result = runner.invoke(app, ["down"])

    assert result.exit_code == 0
    assert "Stopping n8n and keeping the data volume" in result.stderr
    assert "n8n stopped" in result.stderr


def test_cli_status_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))
    instance_dir = tmp_path / "instances" / "default"
    instance_dir.mkdir(parents=True)
    (instance_dir / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")

    def fake_run(args: list[str], cwd: Path) -> CommandResult:
        return CommandResult(args=args, returncode=0, stdout='[{"State":"running"}]', stderr="")

    monkeypatch.setattr("local_n8n.core.instance.run", fake_run)

    result = runner.invoke(app, ["status"])

    assert result.exit_code == 0
    assert "Checking n8n status" in result.stderr
    assert "running" in result.stderr


def test_cli_doctor_failure_exits_with_check_code(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("local_n8n.core.doctor.shutil.which", lambda name: None)
    monkeypatch.setattr(
        "local_n8n.core.doctor._port_check",
        lambda port: DoctorCheck("Port 0", True, "available"),
    )

    def fake_run(args: list[str], cwd: Path) -> CommandResult:
        raise FileNotFoundError("docker")

    monkeypatch.setattr("local_n8n.core.doctor.run", fake_run)

    result = runner.invoke(app, ["doctor", "--port", "0"])

    assert result.exit_code == 10
    assert "Docker CLI" in result.stderr
