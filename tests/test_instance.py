from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import pytest

from local_n8n.compose.template import DEFAULT_IMAGE_REF, LEGACY_DEFAULT_IMAGE_REFS
from local_n8n.core.errors import (
    InstanceNotFoundError,
    LonError,
    PortInUseError,
    PrerequisiteError,
    UsageError,
)
from local_n8n.core.instance import (
    down_instance,
    list_instances,
    logs_instance,
    restart_instance,
    start_instance,
    status_instance,
    stop_instance,
    up_instance,
)
from local_n8n.core.runner import CommandResult
from local_n8n.core.state import StateStore, new_instance_record

ComposeRunner = Callable[[list[str], Path], CommandResult]


def _patch_compose_runners(monkeypatch: pytest.MonkeyPatch, fake_run: ComposeRunner) -> None:
    monkeypatch.setattr("local_n8n.core.instance.run", fake_run)
    monkeypatch.setattr("local_n8n.core.instance.run_streaming", fake_run)


def test_up_instance_renders_and_runs_docker_compose(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[list[str], Path]] = []
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))

    def fake_run(args: list[str], cwd: Path) -> CommandResult:
        calls.append((args, cwd))
        return CommandResult(args=args, returncode=0, stdout="", stderr="")

    _patch_compose_runners(monkeypatch, fake_run)
    monkeypatch.setattr("local_n8n.core.instance.wait_for_web_ui_ready", lambda url: True)

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


def test_up_instance_migrates_legacy_default_image_ref(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))
    instance_dir = tmp_path / "instances" / "default"
    legacy_image_ref = LEGACY_DEFAULT_IMAGE_REFS[0]
    with StateStore(tmp_path / "state.db") as state:
        state.upsert_instance(
            replace(
                new_instance_record(
                    name="default",
                    compose_path=instance_dir / "docker-compose.yml",
                    data_volume="n8n_default_data",
                    port=5678,
                    image_ref=legacy_image_ref,
                    enc_key_ref=instance_dir / ".env",
                    created_at="2026-07-01T00:00:00Z",
                ),
                n8n_version="1.113.3",
            )
        )
    progress: list[str] = []

    def fake_run(args: list[str], cwd: Path) -> CommandResult:
        return CommandResult(args=args, returncode=0, stdout="", stderr="")

    _patch_compose_runners(monkeypatch, fake_run)
    monkeypatch.setattr("local_n8n.core.instance.wait_for_web_ui_ready", lambda url: True)

    result = up_instance("default", progress=progress.append)

    assert result.compose_path.read_text(encoding="utf-8").splitlines()[2] == (
        f"    image: {DEFAULT_IMAGE_REF}"
    )
    with StateStore(tmp_path / "state.db") as state:
        record = state.get_instance("default")
    assert record is not None
    assert record.image_ref == DEFAULT_IMAGE_REF
    assert record.n8n_version is None
    assert "Updating legacy n8n image reference" in progress[0]


def test_up_instance_streams_compose_output_and_reports_steps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))
    stream_calls: list[list[str]] = []
    progress: list[str] = []

    def fail_run(args: list[str], cwd: Path) -> CommandResult:
        raise AssertionError("up should stream Docker Compose output")

    def fake_streaming(args: list[str], cwd: Path) -> CommandResult:
        stream_calls.append(args)
        return CommandResult(args=args, returncode=0, stdout="", stderr="docker progress")

    monkeypatch.setattr("local_n8n.core.instance.run", fail_run)
    monkeypatch.setattr("local_n8n.core.instance.run_streaming", fake_streaming)
    monkeypatch.setattr("local_n8n.core.instance.wait_for_web_ui_ready", lambda url: True)

    up_instance("default", progress=progress.append)

    assert stream_calls[0][-2:] == ["up", "-d"]
    assert progress == [
        "Ensuring local-n8n instance files...",
        "Starting Docker container. First run may download the n8n image...",
        "Waiting for n8n web UI...",
    ]


def test_up_instance_maps_missing_docker_to_prerequisite_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))

    def fake_run(args: list[str], cwd: Path) -> CommandResult:
        raise FileNotFoundError("docker")

    _patch_compose_runners(monkeypatch, fake_run)
    monkeypatch.setattr("local_n8n.core.instance.wait_for_web_ui_ready", lambda url: True)

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

    _patch_compose_runners(monkeypatch, fake_run)
    monkeypatch.setattr("local_n8n.core.instance.wait_for_web_ui_ready", lambda url: True)

    with pytest.raises(PortInUseError) as exc_info:
        up_instance("default")

    assert exc_info.value.exit_code == 11


def test_instance_name_is_validated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))

    with pytest.raises(UsageError):
        up_instance("../bad")


def test_up_instance_waits_for_web_ui_before_returning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))
    ready_urls: list[str] = []

    def fake_run(args: list[str], cwd: Path) -> CommandResult:
        return CommandResult(args=args, returncode=0, stdout="", stderr="")

    def fake_wait(url: str) -> bool:
        ready_urls.append(url)
        return True

    _patch_compose_runners(monkeypatch, fake_run)
    monkeypatch.setattr("local_n8n.core.instance.wait_for_web_ui_ready", fake_wait)

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

    _patch_compose_runners(monkeypatch, fake_run)
    monkeypatch.setattr("local_n8n.core.instance.wait_for_web_ui_ready", lambda url: True)

    result = up_instance("default")

    assert result.url == "http://localhost:5682"
    assert (instance_dir / ".env").read_text(encoding="utf-8").startswith("N8N_ENCRYPTION_KEY=keep")


def test_status_instance_parses_compose_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))
    _write_phase_zero_compose(tmp_path)
    calls: list[list[str]] = []

    def fake_run(args: list[str], cwd: Path) -> CommandResult:
        calls.append(args)
        return CommandResult(
            args=args,
            returncode=0,
            stdout='[{"Service":"n8n","State":"running","Health":"healthy"}]',
            stderr="",
        )

    _patch_compose_runners(monkeypatch, fake_run)
    monkeypatch.setattr("local_n8n.core.instance.is_web_ui_ready", lambda url: True)

    result = status_instance("default")

    assert result.container_state == "running"
    assert result.web_ui_state == "reachable"
    assert "--all" in calls[0]


def test_status_instance_includes_stopped_containers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))
    _write_phase_zero_compose(tmp_path)

    def fake_run(args: list[str], cwd: Path) -> CommandResult:
        return CommandResult(args=args, returncode=0, stdout='[{"State":"exited"}]', stderr="")

    _patch_compose_runners(monkeypatch, fake_run)

    result = status_instance("default")

    assert result.container_state == "exited"


def test_status_instance_reports_missing_container_as_not_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))
    _write_phase_zero_compose(tmp_path)

    def fake_run(args: list[str], cwd: Path) -> CommandResult:
        return CommandResult(args=args, returncode=0, stdout="", stderr="")

    _patch_compose_runners(monkeypatch, fake_run)

    result = status_instance("default")

    assert result.container_state == "not present"


def test_list_instances_returns_registered_instances_with_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))
    with StateStore(tmp_path / "state.db") as state:
        state.upsert_instance(
            new_instance_record(
                name="alpha",
                compose_path=tmp_path / "instances" / "alpha" / "docker-compose.yml",
                data_volume="n8n_alpha_data",
                port=5680,
                enc_key_ref=tmp_path / "instances" / "alpha" / ".env",
                created_at="2026-07-01T00:00:00Z",
            )
        )
        state.upsert_instance(
            new_instance_record(
                name="beta",
                compose_path=tmp_path / "instances" / "beta" / "docker-compose.yml",
                data_volume="n8n_beta_data",
                port=5681,
                enc_key_ref=tmp_path / "instances" / "beta" / ".env",
                created_at="2026-07-01T00:00:00Z",
            )
        )

    def fake_run(args: list[str], cwd: Path) -> CommandResult:
        state = "running" if "alpha" in str(cwd) else "exited"
        return CommandResult(args=args, returncode=0, stdout=f'[{{"State":"{state}"}}]', stderr="")

    _patch_compose_runners(monkeypatch, fake_run)

    results = list_instances()

    assert [result.name for result in results] == ["alpha", "beta"]
    assert [result.container_state for result in results] == ["running", "exited"]
    assert results[0].url == "http://localhost:5680"


def test_logs_instance_returns_compose_logs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))
    _write_phase_zero_compose(tmp_path)

    def fake_run(args: list[str], cwd: Path) -> CommandResult:
        return CommandResult(args=args, returncode=0, stdout="n8n ready\n", stderr="")

    _patch_compose_runners(monkeypatch, fake_run)

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

    _patch_compose_runners(monkeypatch, fake_run)
    monkeypatch.setattr("local_n8n.core.instance.wait_for_web_ui_ready", fake_wait)

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

    _patch_compose_runners(monkeypatch, fake_run)
    monkeypatch.setattr("local_n8n.core.instance.wait_for_web_ui_ready", fake_wait)

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

    _patch_compose_runners(monkeypatch, fake_run)

    result = stop_instance("default")

    assert result.volume_name == "n8n_default_data"
    assert calls[-1][-1] == "stop"


@pytest.mark.parametrize(
    ("command", "docker_action", "expected_progress"),
    [
        (down_instance, "down", "Running Docker Compose down..."),
        (stop_instance, "stop", "Running Docker Compose stop..."),
    ],
)
def test_non_waiting_lifecycle_commands_stream_compose_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    command,
    docker_action: str,
    expected_progress: str,
) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))
    _write_phase_zero_compose(tmp_path)
    stream_calls: list[list[str]] = []
    progress: list[str] = []

    def fail_run(args: list[str], cwd: Path) -> CommandResult:
        raise AssertionError(f"{docker_action} should stream Docker Compose output")

    def fake_streaming(args: list[str], cwd: Path) -> CommandResult:
        stream_calls.append(args)
        return CommandResult(args=args, returncode=0, stdout="", stderr="docker progress")

    monkeypatch.setattr("local_n8n.core.instance.run", fail_run)
    monkeypatch.setattr("local_n8n.core.instance.run_streaming", fake_streaming)

    command("default", progress=progress.append)

    assert stream_calls[0][-1] == docker_action
    assert progress == [expected_progress]


@pytest.mark.parametrize(
    ("command", "docker_action", "expected_progress"),
    [
        (start_instance, "start", "Running Docker Compose start..."),
        (restart_instance, "restart", "Running Docker Compose restart..."),
    ],
)
def test_waiting_lifecycle_commands_stream_compose_output_after_status_check(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    command,
    docker_action: str,
    expected_progress: str,
) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))
    _write_phase_zero_compose(tmp_path)
    captured_calls: list[list[str]] = []
    stream_calls: list[list[str]] = []
    progress: list[str] = []

    def fake_run(args: list[str], cwd: Path) -> CommandResult:
        captured_calls.append(args)
        return CommandResult(args=args, returncode=0, stdout='[{"State":"exited"}]', stderr="")

    def fake_streaming(args: list[str], cwd: Path) -> CommandResult:
        stream_calls.append(args)
        return CommandResult(args=args, returncode=0, stdout="", stderr="docker progress")

    monkeypatch.setattr("local_n8n.core.instance.run", fake_run)
    monkeypatch.setattr("local_n8n.core.instance.run_streaming", fake_streaming)
    monkeypatch.setattr("local_n8n.core.instance.wait_for_web_ui_ready", lambda url: True)

    command("default", progress=progress.append)

    assert captured_calls[0][-3:] == ["--all", "--format", "json"]
    assert stream_calls[0][-1] == docker_action
    assert progress == [expected_progress, "Waiting for n8n web UI..."]


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
