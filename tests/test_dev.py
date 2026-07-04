from __future__ import annotations

from pathlib import Path

import pytest

from local_n8n.compose.template import DEFAULT_IMAGE_REF
from local_n8n.core.dev import plan_dev_wipe, wipe_dev
from local_n8n.core.runner import CommandResult
from local_n8n.core.state import StateStore, new_instance_record


def test_plan_dev_wipe_collects_registered_instances_and_instance_dirs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))
    with StateStore(tmp_path / "state.db") as state:
        state.upsert_instance(
            new_instance_record(
                name="alpha",
                compose_path=tmp_path / "instances" / "alpha" / "docker-compose.yml",
                data_volume="n8n_alpha_data.g2",
                port=5680,
                enc_key_ref=tmp_path / "instances" / "alpha" / ".env",
                created_at="2026-07-01T00:00:00Z",
            )
        )
    (tmp_path / "instances" / "beta").mkdir(parents=True)
    (tmp_path / "instances" / "not valid").mkdir(parents=True)

    plan = plan_dev_wipe()

    assert [target.name for target in plan.targets] == ["alpha", "beta"]
    assert [target.project_name for target in plan.targets] == [
        "local-n8n-alpha",
        "local-n8n-beta",
    ]
    assert set(plan.volume_names) == {
        "n8n_alpha_data",
        "n8n_alpha_data.g2",
        "n8n_beta_data",
    }
    assert plan.image_refs == ()
    assert tmp_path / "instances" in plan.local_paths
    assert tmp_path / "state.db" in plan.local_paths


def test_plan_dev_wipe_can_include_known_images(
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
                image_ref="example.test/n8n:custom@sha256:abc",
                enc_key_ref=tmp_path / "instances" / "alpha" / ".env",
                created_at="2026-07-01T00:00:00Z",
            )
        )
    (tmp_path / "instances" / "beta").mkdir(parents=True)

    plan = plan_dev_wipe(include_images=True)

    assert DEFAULT_IMAGE_REF in plan.image_refs
    assert "example.test/n8n:custom@sha256:abc" in plan.image_refs
    assert "example.test/n8n:custom" in plan.image_refs


def test_plan_dev_wipe_includes_default_image_even_after_state_is_gone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))

    plan = plan_dev_wipe(include_images=True)

    assert plan.image_refs == (DEFAULT_IMAGE_REF,)


def test_wipe_dev_removes_docker_objects_and_local_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))
    instance_dir = tmp_path / "instances" / "alpha"
    instance_dir.mkdir(parents=True)
    compose_path = instance_dir / "docker-compose.yml"
    compose_path.write_text("services: {}\n", encoding="utf-8")
    with StateStore(tmp_path / "state.db") as state:
        state.upsert_instance(
            new_instance_record(
                name="alpha",
                compose_path=compose_path,
                data_volume="n8n_alpha_data",
                port=5680,
                enc_key_ref=instance_dir / ".env",
                created_at="2026-07-01T00:00:00Z",
            )
        )

    captured: list[list[str]] = []
    progress: list[str] = []

    def fake_run(args: list[str], cwd: Path) -> CommandResult:
        captured.append(args)
        if args[:3] == ["docker", "container", "ls"]:
            return CommandResult(args=args, returncode=0, stdout="container-id\n", stderr="")
        if args[:3] == ["docker", "network", "ls"]:
            return CommandResult(args=args, returncode=0, stdout="", stderr="")
        if args[:3] == ["docker", "volume", "ls"]:
            return CommandResult(args=args, returncode=0, stdout="label-volume\n", stderr="")
        return CommandResult(args=args, returncode=0, stdout="", stderr="")

    def fake_streaming(args: list[str], cwd: Path) -> CommandResult:
        captured.append(args)
        return CommandResult(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr("local_n8n.core.dev.run", fake_run)
    monkeypatch.setattr("local_n8n.core.dev.run_streaming", fake_streaming)

    result = wipe_dev(progress=progress.append)

    assert any(command[-3:] == ["down", "-v", "--remove-orphans"] for command in captured)
    assert ["docker", "container", "rm", "--force", "container-id"] in captured
    assert ["docker", "volume", "rm", "--force", "label-volume"] in captured
    assert ["docker", "volume", "rm", "--force", "n8n_alpha_data"] in captured
    assert not (tmp_path / "instances").exists()
    assert not (tmp_path / "state.db").exists()
    assert result.deleted_paths
    assert "Deleting local instance files and state..." in progress


def test_wipe_dev_removes_images_when_planned(
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
                image_ref="example.test/n8n:custom@sha256:abc",
                enc_key_ref=tmp_path / "instances" / "alpha" / ".env",
                created_at="2026-07-01T00:00:00Z",
            )
        )

    captured: list[list[str]] = []

    def fake_run(args: list[str], cwd: Path) -> CommandResult:
        captured.append(args)
        return CommandResult(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr("local_n8n.core.dev.run", fake_run)
    monkeypatch.setattr("local_n8n.core.dev.run_streaming", fake_run)

    wipe_dev(plan_dev_wipe(include_images=True))

    assert ["docker", "image", "rm", "--force", "example.test/n8n:custom@sha256:abc"] in captured


def test_wipe_dev_with_images_after_state_is_gone_removes_default_image_refs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))
    captured: list[list[str]] = []

    def fake_run(args: list[str], cwd: Path) -> CommandResult:
        captured.append(args)
        return CommandResult(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr("local_n8n.core.dev.run", fake_run)
    monkeypatch.setattr("local_n8n.core.dev.run_streaming", fake_run)

    result = wipe_dev(plan_dev_wipe(include_images=True))

    assert ["docker", "image", "rm", "--force", DEFAULT_IMAGE_REF] in captured
    assert result.plan.targets == ()
    assert result.plan.volume_names == ()
    assert result.deleted_paths == ()
