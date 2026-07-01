from __future__ import annotations

from pathlib import Path

import pytest

from local_n8n.core.errors import (
    InstanceNotFoundError,
    LonError,
    PortInUseError,
    PrerequisiteError,
    UsageError,
)
from local_n8n.core.instance import (
    logs_instance,
    restart_instance,
    start_instance,
    status_instance,
    stop_instance,
    up_instance,
)
from local_n8n.core.runner import CommandResult


def test_up_instance_renders_and_runs_docker_compose(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[list[str], Path]] = []
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))

    def fake_run(args: list[str], cwd: Path) -> CommandResult:
        calls.append((args, cwd))
        return CommandResult(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr("local_n8n.core.instance.run", fake_run)
    monkeypatch.setattr("local_n8n.core.instance.wait_for_http_ready", lambda url: True)

    result = up_instance("default", port=5678)

    assert result.url == "http://localhost:5678"
    assert result.compose_path == tmp_path / "instances" / "default" / "docker-compose.yml"
    assert calls == [
        (
            [
                "docker",
                "compose",
                "-p",
                "local-n8n-default",
                "-f",
                str(result.compose_path),
                "up",
                "-d",
            ],
            tmp_path / "instances" / "default",
        )
    ]
    assert (tmp_path / "state.db").exists()


def test_up_instance_maps_missing_docker_to_prerequisite_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))

    def fake_run(args: list[str], cwd: Path) -> CommandResult:
        raise FileNotFoundError("docker")

    monkeypatch.setattr("local_n8n.core.instance.run", fake_run)
    monkeypatch.setattr("local_n8n.core.instance.wait_for_http_ready", lambda url: True)

    with pytest.raises(PrerequisiteError) as exc_info:
        up_instance("default")

    assert exc_info.value.exit_code == 10


def test_up_instance_maps_port_conflict(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))

    def fake_run(args: list[str], cwd: Path) -> CommandResult:
        return CommandResult(
            args=args,
            returncode=1,
            stdout="",
            stderr="Bind for 0.0.0.0:5678 failed: port is already allocated",
        )

    monkeypatch.setattr("local_n8n.core.instance.run", fake_run)
    monkeypatch.setattr("local_n8n.core.instance.wait_for_http_ready", lambda url: True)

    with pytest.raises(PortInUseError) as exc_info:
        up_instance("default")

    assert exc_info.value.exit_code == 11


def test_instance_name_is_validated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))

    with pytest.raises(UsageError):
        up_instance("../bad")


def test_up_instance_waits_for_editor_before_returning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))
    ready_urls: list[str] = []

    def fake_run(args: list[str], cwd: Path) -> CommandResult:
        return CommandResult(args=args, returncode=0, stdout="", stderr="")

    def fake_wait(url: str) -> bool:
        ready_urls.append(url)
        return True

    monkeypatch.setattr("local_n8n.core.instance.run", fake_run)
    monkeypatch.setattr("local_n8n.core.instance.wait_for_http_ready", fake_wait)

    up_instance("default", port=5680)

    assert ready_urls == ["http://localhost:5680"]


def test_up_instance_adopts_existing_phase_zero_env_port(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))
    instance_dir = tmp_path / "instances" / "default"
    instance_dir.mkdir(parents=True)
    (instance_dir / ".env").write_text("N8N_ENCRYPTION_KEY=keep\nN8N_PORT=5682\n", encoding="utf-8")
    calls: list[list[str]] = []

    def fake_run(args: list[str], cwd: Path) -> CommandResult:
        calls.append(args)
        return CommandResult(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr("local_n8n.core.instance.run", fake_run)
    monkeypatch.setattr("local_n8n.core.instance.wait_for_http_ready", lambda url: True)

    result = up_instance("default")

    assert result.url == "http://localhost:5682"
    assert (instance_dir / ".env").read_text(encoding="utf-8").startswith("N8N_ENCRYPTION_KEY=keep")


def test_status_instance_parses_compose_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))
    _write_phase_zero_compose(tmp_path)

    def fake_run(args: list[str], cwd: Path) -> CommandResult:
        return CommandResult(
            args=args,
            returncode=0,
            stdout='[{"Service":"n8n","State":"running","Health":"healthy"}]',
            stderr="",
        )

    monkeypatch.setattr("local_n8n.core.instance.run", fake_run)

    result = status_instance("default")

    assert result.container_state == "running"
    assert result.health == "healthy"


def test_status_instance_reports_missing_container_as_not_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))
    _write_phase_zero_compose(tmp_path)

    def fake_run(args: list[str], cwd: Path) -> CommandResult:
        return CommandResult(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr("local_n8n.core.instance.run", fake_run)

    result = status_instance("default")

    assert result.container_state == "not present"


def test_logs_instance_returns_compose_logs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))
    _write_phase_zero_compose(tmp_path)

    def fake_run(args: list[str], cwd: Path) -> CommandResult:
        return CommandResult(args=args, returncode=0, stdout="n8n ready\n", stderr="")

    monkeypatch.setattr("local_n8n.core.instance.run", fake_run)

    result = logs_instance("default", tail=50)

    assert result.output == "n8n ready\n"


def test_restart_instance_fails_fast_when_container_is_not_created(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))
    _write_phase_zero_compose(tmp_path)
    readiness_called = False

    def fake_run(args: list[str], cwd: Path) -> CommandResult:
        if "ps" in args:
            return CommandResult(args=args, returncode=0, stdout="", stderr="")
        return CommandResult(args=args, returncode=0, stdout="", stderr="")

    def fake_wait(url: str) -> bool:
        nonlocal readiness_called
        readiness_called = True
        return True

    monkeypatch.setattr("local_n8n.core.instance.run", fake_run)
    monkeypatch.setattr("local_n8n.core.instance.wait_for_http_ready", fake_wait)

    with pytest.raises(LonError) as exc_info:
        restart_instance("default")

    assert "no container to restart" in exc_info.value.message
    assert not readiness_called


def test_start_instance_fails_fast_when_container_is_not_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))
    _write_phase_zero_compose(tmp_path)
    readiness_called = False

    def fake_run(args: list[str], cwd: Path) -> CommandResult:
        if "ps" in args:
            return CommandResult(args=args, returncode=0, stdout="", stderr="")
        return CommandResult(args=args, returncode=0, stdout="", stderr="")

    def fake_wait(url: str) -> bool:
        nonlocal readiness_called
        readiness_called = True
        return True

    monkeypatch.setattr("local_n8n.core.instance.run", fake_run)
    monkeypatch.setattr("local_n8n.core.instance.wait_for_http_ready", fake_wait)

    with pytest.raises(LonError) as exc_info:
        start_instance("default")

    assert "no container to start" in exc_info.value.message
    assert not readiness_called


def test_stop_instance_uses_compose_stop(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))
    _write_phase_zero_compose(tmp_path)
    calls: list[list[str]] = []

    def fake_run(args: list[str], cwd: Path) -> CommandResult:
        calls.append(args)
        return CommandResult(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr("local_n8n.core.instance.run", fake_run)

    result = stop_instance("default")

    assert result.volume_name == "n8n_default_data"
    assert calls[-1][-1] == "stop"


def test_status_instance_requires_existing_instance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))

    with pytest.raises(InstanceNotFoundError) as exc_info:
        status_instance("missing")

    assert exc_info.value.exit_code == 13


def _write_phase_zero_compose(config_home: Path) -> None:
    instance_dir = config_home / "instances" / "default"
    instance_dir.mkdir(parents=True)
    (instance_dir / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
