from __future__ import annotations

from pathlib import Path

import pytest

from local_n8n.core.errors import PortInUseError, PrerequisiteError, UsageError
from local_n8n.core.instance import up_instance
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
