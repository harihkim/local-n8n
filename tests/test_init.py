from __future__ import annotations

from pathlib import Path

import pytest

from local_n8n.core.doctor import DoctorCheck, DoctorReport
from local_n8n.core.errors import PrerequisiteError, UsageError
from local_n8n.core.init import InitState, InitStep, init_instance, plan_init
from local_n8n.core.instance import ImageUpdateConfirm, OpenResult, ProgressReporter, UpResult
from local_n8n.core.state import StateStore, new_instance_record


def test_plan_init_for_new_instance_has_no_side_effects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))

    plan = plan_init("default")

    assert plan.state == InitState.NEW
    assert plan.instance_name == "default"
    assert plan.requested_port is None
    assert plan.port == 5678
    assert plan.url == "http://localhost:5678"
    assert plan.compose_path == tmp_path / "instances" / "default" / "docker-compose.yml"
    assert plan.env_path == tmp_path / "instances" / "default" / ".env"
    assert plan.volume_name == "n8n_default_data"
    assert not plan.registered
    assert not plan.compose_exists
    assert not plan.env_exists
    assert plan.will_create_compose
    assert plan.will_create_env
    assert not plan.will_preserve_env
    assert plan.will_register
    assert plan.will_start
    assert plan.will_open
    assert not plan.requested_port_ignored
    assert plan.steps == (
        InitStep.CHECK_PREREQUISITES,
        InitStep.ENSURE_INSTANCE_FILES,
        InitStep.REGISTER_INSTANCE,
        InitStep.START_INSTANCE,
        InitStep.OPEN_WEB_UI,
        InitStep.EXPLAIN_OWNER_SETUP,
    )
    assert not (tmp_path / "state.db").exists()
    assert not (tmp_path / "instances").exists()


def test_plan_init_adopts_existing_files_and_env_port(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))
    instance_dir = tmp_path / "instances" / "default"
    instance_dir.mkdir(parents=True)
    (instance_dir / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    (instance_dir / ".env").write_text(
        "N8N_ENCRYPTION_KEY=keep\nN8N_PORT=5682\n",
        encoding="utf-8",
    )

    plan = plan_init("default", open_browser=False)

    assert plan.state == InitState.ADOPTABLE
    assert plan.port == 5682
    assert plan.url == "http://localhost:5682"
    assert plan.compose_exists
    assert plan.env_exists
    assert not plan.will_create_compose
    assert not plan.will_create_env
    assert plan.will_preserve_env
    assert plan.will_register
    assert not plan.will_open
    assert InitStep.OPEN_WEB_UI not in plan.steps
    assert not (tmp_path / "state.db").exists()


def test_plan_init_uses_registered_instance_and_ignores_conflicting_port(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))
    with StateStore(tmp_path / "state.db") as state:
        state.upsert_instance(
            new_instance_record(
                name="default",
                compose_path=tmp_path / "instances" / "default" / "docker-compose.yml",
                data_volume="n8n_default_data",
                port=5689,
                enc_key_ref=tmp_path / "instances" / "default" / ".env",
                created_at="2026-07-04T00:00:00Z",
            )
        )

    plan = plan_init("default", port=5678)

    assert plan.state == InitState.INITIALIZED
    assert plan.registered
    assert plan.port == 5689
    assert plan.requested_port == 5678
    assert plan.requested_port_ignored
    assert not plan.will_register
    assert InitStep.REGISTER_INSTANCE not in plan.steps


def test_plan_init_requested_port_is_used_for_new_instance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))

    plan = plan_init("preview", port=5688)

    assert plan.state == InitState.NEW
    assert plan.port == 5688
    assert plan.url == "http://localhost:5688"
    assert plan.compose_path == tmp_path / "instances" / "preview" / "docker-compose.yml"
    assert plan.volume_name == "n8n_preview_data"


def test_plan_init_validates_instance_name(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))

    with pytest.raises(UsageError):
        plan_init("../bad")


def test_init_instance_checks_prereqs_starts_and_opens(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))
    progress: list[str] = []
    up_calls: list[tuple[str, int | None]] = []
    image_confirm_calls: list[tuple[str, str]] = []

    def fake_run_doctor(port: int, check_port: bool = True) -> DoctorReport:
        assert port == 5688
        assert not check_port
        return DoctorReport([DoctorCheck("Docker CLI", True, "available")])

    def fake_image_update_confirm(old: str, new: str) -> bool:
        image_confirm_calls.append((old, new))
        return True

    def fake_up_instance(
        instance_name: str,
        port: int | None = None,
        progress: ProgressReporter | None = None,
        image_update_confirm: ImageUpdateConfirm | None = None,
    ) -> UpResult:
        up_calls.append((instance_name, port))
        assert image_update_confirm is not None
        assert image_update_confirm("old", "new")
        if progress is not None:
            progress("fake up progress")
        return UpResult(
            url=f"http://localhost:{port}",
            compose_path=tmp_path / "instances" / instance_name / "docker-compose.yml",
            volume_name=f"n8n_{instance_name}_data",
        )

    monkeypatch.setattr("local_n8n.core.init.run_doctor", fake_run_doctor)
    monkeypatch.setattr("local_n8n.core.init.up_instance", fake_up_instance)
    monkeypatch.setattr(
        "local_n8n.core.init.open_instance",
        lambda instance_name: OpenResult(
            url="http://localhost:5688",
            opened=True,
            opener="wslview",
        ),
    )

    result = init_instance(
        instance_name="preview",
        port=5688,
        open_browser=True,
        progress=progress.append,
        image_update_confirm=fake_image_update_confirm,
    )

    assert result.started
    assert result.opened
    assert result.opener == "wslview"
    assert result.plan.url == "http://localhost:5688"
    assert up_calls == [("preview", 5688)]
    assert image_confirm_calls == [("old", "new")]
    assert progress == [
        "Preparing local-n8n instance 'preview'...",
        "Checking Docker prerequisites...",
        "Docker prerequisites look ready.",
        "fake up progress",
        "Opening n8n web UI...",
    ]


def test_init_instance_maps_prereq_failure_to_prerequisite_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))

    monkeypatch.setattr(
        "local_n8n.core.init.run_doctor",
        lambda port, check_port=True: DoctorReport(
            [
                DoctorCheck(
                    "Docker CLI",
                    False,
                    "not found",
                    hint="Install Docker Engine inside WSL/Linux.",
                    exit_code=10,
                )
            ]
        ),
    )

    with pytest.raises(PrerequisiteError) as exc_info:
        init_instance()

    assert "Docker CLI is not ready" in exc_info.value.message
    assert exc_info.value.exit_code == 10
