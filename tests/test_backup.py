from __future__ import annotations

import json
import tarfile
from io import BytesIO
from pathlib import Path
from typing import Any, cast

import pytest

from local_n8n.core.backup import backup_instance
from local_n8n.core.crypto import open_bundle
from local_n8n.core.errors import CommandFailedError
from local_n8n.core.runner import CommandResult
from local_n8n.core.state import StateStore, new_instance_record


def test_backup_instance_creates_encrypted_bundle_and_records_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))
    _seed_instance(tmp_path)

    def fake_run(args: list[str], cwd: Path) -> CommandResult:
        if args[:2] == ["docker", "compose"] and "ps" in args:
            return CommandResult(args=args, returncode=0, stdout='[{"State":"exited"}]', stderr="")
        if args[:2] == ["docker", "run"]:
            _write_volume_tar(cwd / "volume.tar")
            return CommandResult(args=args, returncode=0, stdout="", stderr="")
        return CommandResult(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr("local_n8n.core.backup.run", fake_run)
    monkeypatch.setattr("local_n8n.core.backup.run_streaming", fake_run)

    bundle_path = tmp_path / "manual.n8nbundle"
    result = backup_instance(
        "default",
        passphrase="backup-passphrase",
        output_path=bundle_path,
        recovery_code_factory=lambda: "recovery-code",
    )

    assert result.bundle_path == bundle_path
    assert result.recovery_code == "recovery-code"
    assert not result.restarted
    assert bundle_path.read_bytes().startswith(b"N8NB")

    opened = open_bundle(bundle_path.read_bytes(), secret="backup-passphrase")
    manifest = _manifest_from_payload(opened.payload)
    assert manifest["instance"] == "default"
    manifest_files = _manifest_files(manifest)
    assert manifest_files[0]["path"] == ".env"
    assert {file["path"] for file in manifest_files} == {
        ".env",
        "docker-compose.yml",
        "volume.tar",
    }

    with StateStore(tmp_path / "state.db") as state:
        backups = state.list_backups("default")
    assert len(backups) == 1
    assert backups[0].location == bundle_path
    assert backups[0].checksum == result.checksum
    assert backups[0].size == result.size


def test_backup_instance_restarts_running_container_in_finally(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))
    _seed_instance(tmp_path)
    calls: list[list[str]] = []

    def fake_run(args: list[str], cwd: Path) -> CommandResult:
        calls.append(args)
        if args[:2] == ["docker", "compose"] and "ps" in args:
            return CommandResult(args=args, returncode=0, stdout='[{"State":"running"}]', stderr="")
        if args[:2] == ["docker", "run"]:
            _write_volume_tar(cwd / "volume.tar")
        return CommandResult(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr("local_n8n.core.backup.run", fake_run)
    monkeypatch.setattr("local_n8n.core.backup.run_streaming", fake_run)
    monkeypatch.setattr("local_n8n.core.backup.wait_for_web_ui_ready", lambda url: True)

    result = backup_instance(
        "default",
        passphrase="backup-passphrase",
        output_path=tmp_path / "running.n8nbundle",
        recovery_code_factory=lambda: "recovery-code",
    )

    assert result.restarted
    assert any(command[-2:] == ["stop", "n8n"] for command in calls)
    assert any(command[-2:] == ["start", "n8n"] for command in calls)


def test_backup_instance_restarts_running_container_after_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))
    _seed_instance(tmp_path)
    calls: list[list[str]] = []

    def fake_run(args: list[str], cwd: Path) -> CommandResult:
        calls.append(args)
        if args[:2] == ["docker", "compose"] and "ps" in args:
            return CommandResult(args=args, returncode=0, stdout='[{"State":"running"}]', stderr="")
        if args[:2] == ["docker", "run"]:
            return CommandResult(args=args, returncode=1, stdout="", stderr="tar failed")
        return CommandResult(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr("local_n8n.core.backup.run", fake_run)
    monkeypatch.setattr("local_n8n.core.backup.run_streaming", fake_run)
    monkeypatch.setattr("local_n8n.core.backup.wait_for_web_ui_ready", lambda url: True)

    with pytest.raises(CommandFailedError):
        backup_instance(
            "default",
            passphrase="backup-passphrase",
            output_path=tmp_path / "failed.n8nbundle",
            recovery_code_factory=lambda: "recovery-code",
        )

    assert any(command[-2:] == ["start", "n8n"] for command in calls)


def test_backup_instance_reuses_existing_recovery_material(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))
    _seed_instance(tmp_path)

    def fake_run(args: list[str], cwd: Path) -> CommandResult:
        if args[:2] == ["docker", "compose"] and "ps" in args:
            return CommandResult(args=args, returncode=0, stdout="", stderr="")
        if args[:2] == ["docker", "run"]:
            _write_volume_tar(cwd / "volume.tar")
        return CommandResult(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr("local_n8n.core.backup.run", fake_run)
    monkeypatch.setattr("local_n8n.core.backup.run_streaming", fake_run)

    first = backup_instance(
        "default",
        passphrase="backup-passphrase",
        output_path=tmp_path / "first.n8nbundle",
        recovery_code_factory=lambda: "recovery-code",
    )
    second = backup_instance(
        "default",
        passphrase="backup-passphrase",
        output_path=tmp_path / "second.n8nbundle",
        recovery_code_factory=lambda: pytest.fail("recovery code should be reused"),
    )

    assert first.recovery_code == "recovery-code"
    assert second.recovery_code is None
    opened = open_bundle(second.bundle_path.read_bytes(), secret="recovery-code")
    assert _manifest_from_payload(opened.payload)["instance"] == "default"


def _seed_instance(tmp_path: Path) -> None:
    instance_dir = tmp_path / "instances" / "default"
    instance_dir.mkdir(parents=True)
    compose_path = instance_dir / "docker-compose.yml"
    env_path = instance_dir / ".env"
    compose_path.write_text("services:\n  n8n: {}\n", encoding="utf-8")
    env_path.write_text("N8N_ENCRYPTION_KEY=test-key\n", encoding="utf-8")
    with StateStore(tmp_path / "state.db") as state:
        state.upsert_instance(
            new_instance_record(
                name="default",
                compose_path=compose_path,
                data_volume="n8n_default_data",
                port=5678,
                enc_key_ref=env_path,
                created_at="2026-07-01T00:00:00Z",
            )
        )


def _write_volume_tar(path: Path) -> None:
    source = path.parent / "data.txt"
    source.write_text("workflow data", encoding="utf-8")
    with tarfile.open(path, "w") as archive:
        archive.add(source, arcname="data.txt")


def _manifest_from_payload(payload: bytes) -> dict[str, Any]:
    with tarfile.open(fileobj=BytesIO(payload), mode="r") as archive:
        member = archive.extractfile("manifest.json")
        assert member is not None
        parsed = json.loads(member.read().decode("utf-8"))
    assert isinstance(parsed, dict)
    return parsed


def _manifest_files(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    files = manifest["files"]
    assert isinstance(files, list)
    return cast(list[dict[str, Any]], files)
