from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from local_n8n.app import app
from local_n8n.core.doctor import DoctorCheck
from local_n8n.core.runner import CommandResult
from local_n8n.core.state import StateStore, new_instance_record

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
    assert "Removing n8n container and keeping the data volume" in result.stderr
    assert "n8n container removed" in result.stderr


def test_cli_stop_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))
    instance_dir = tmp_path / "instances" / "default"
    instance_dir.mkdir(parents=True)
    (instance_dir / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")

    def fake_run(args: list[str], cwd: Path) -> CommandResult:
        return CommandResult(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr("local_n8n.core.instance.run", fake_run)

    result = runner.invoke(app, ["stop"])

    assert result.exit_code == 0
    assert "Stopping n8n container" in result.stderr
    assert "Container kept" in result.stderr


def test_cli_start_fails_fast_when_container_is_not_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))
    instance_dir = tmp_path / "instances" / "default"
    instance_dir.mkdir(parents=True)
    (instance_dir / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")

    def fake_run(args: list[str], cwd: Path) -> CommandResult:
        if "ps" in args:
            return CommandResult(args=args, returncode=0, stdout="", stderr="")
        return CommandResult(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr("local_n8n.core.instance.run", fake_run)
    monkeypatch.setattr("local_n8n.core.instance.wait_for_http_ready", lambda url: True)

    result = runner.invoke(app, ["start"])

    assert result.exit_code == 1
    assert "no container to start" in result.stderr
    assert "Run `lon up --instance default`" in result.stderr


def test_cli_restart_fails_fast_when_container_is_not_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))
    instance_dir = tmp_path / "instances" / "default"
    instance_dir.mkdir(parents=True)
    (instance_dir / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")

    def fake_run(args: list[str], cwd: Path) -> CommandResult:
        if "ps" in args:
            return CommandResult(args=args, returncode=0, stdout="", stderr="")
        return CommandResult(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr("local_n8n.core.instance.run", fake_run)
    monkeypatch.setattr("local_n8n.core.instance.wait_for_http_ready", lambda url: True)

    result = runner.invoke(app, ["restart"])

    assert result.exit_code == 1
    assert "no container to restart" in result.stderr
    assert "Run `lon up --instance default`" in result.stderr


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


def test_cli_list_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))
    with StateStore(tmp_path / "state.db") as state:
        state.upsert_instance(
            new_instance_record(
                name="manual-check",
                compose_path=tmp_path / "instances" / "manual-check" / "docker-compose.yml",
                data_volume="n8n_manual-check_data",
                port=5683,
                enc_key_ref=tmp_path / "instances" / "manual-check" / ".env",
                created_at="2026-07-01T00:00:00Z",
            )
        )

    def fake_run(args: list[str], cwd: Path) -> CommandResult:
        return CommandResult(args=args, returncode=0, stdout='[{"State":"running"}]', stderr="")

    monkeypatch.setattr("local_n8n.core.instance.run", fake_run)

    result = runner.invoke(app, ["list"])

    assert result.exit_code == 0
    assert "manual-check" in result.stderr
    assert "running" in result.stderr
    assert "Use `lon status --instance <name>` for details." in result.stderr


def test_cli_list_empty_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))

    result = runner.invoke(app, ["list"])

    assert result.exit_code == 0
    assert "No local-n8n instances yet" in result.stderr
    assert "Use `lon status --instance <name>`" not in result.stderr


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
