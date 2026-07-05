from __future__ import annotations

import hashlib
import json
import tarfile
from io import BytesIO
from pathlib import Path
from typing import Any, cast

import pytest

from local_n8n.core.backup import (
    BackupResult,
    backup_instance,
    restore_instance,
    reveal_recovery_code,
)
from local_n8n.core.crypto import open_bundle, seal_bundle
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


def test_reveal_recovery_code_unlocks_existing_recovery_material(
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
    backup_instance(
        "default",
        passphrase="backup-passphrase",
        output_path=tmp_path / "first.n8nbundle",
        recovery_code_factory=lambda: "recovery-code",
    )

    assert reveal_recovery_code("default", passphrase="backup-passphrase") == "recovery-code"


def test_reveal_recovery_code_requires_existing_recovery_material(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))
    _seed_instance(tmp_path)

    with pytest.raises(Exception) as exc_info:
        reveal_recovery_code("default", passphrase="backup-passphrase")

    assert "does not exist" in str(exc_info.value)


def test_restore_instance_restores_bundle_to_new_instance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))
    bundle_path = _write_restore_bundle(tmp_path, instance="restored")
    calls: list[list[str]] = []

    def fake_run(args: list[str], cwd: Path) -> CommandResult:
        calls.append(args)
        return CommandResult(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr("local_n8n.core.backup.run", fake_run)
    monkeypatch.setattr("local_n8n.core.backup.run_streaming", fake_run)
    monkeypatch.setattr("local_n8n.core.backup.wait_for_web_ui_ready", lambda url: True)

    result = restore_instance(bundle_path, secret="restore-secret", port=5691)

    assert result.instance == "restored"
    assert result.url == "http://localhost:5691"
    assert result.volume_name.startswith("n8n_restored_data.g")
    assert (tmp_path / "instances" / "restored" / ".env").read_text(encoding="utf-8").splitlines()[
        1
    ] == "N8N_PORT=5691"
    assert any(command[:3] == ["docker", "volume", "create"] for command in calls)
    assert any(command[:2] == ["docker", "run"] for command in calls)
    assert any(command[-2:] == ["up", "-d"] for command in calls)
    with StateStore(tmp_path / "state.db") as state:
        record = state.get_instance("restored")
    assert record is not None
    assert record.port == 5691
    assert record.data_volume == result.volume_name


def test_first_backup_after_restore_creates_new_recovery_material(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))
    bundle_path = _write_restore_bundle(tmp_path, instance="restored")

    def fake_run(args: list[str], cwd: Path) -> CommandResult:
        if args[:2] == ["docker", "compose"] and "ps" in args:
            return CommandResult(args=args, returncode=0, stdout="", stderr="")
        if args[:2] == ["docker", "run"] and "-cf" in args:
            _write_volume_tar(cwd / "volume.tar")
        return CommandResult(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr("local_n8n.core.backup.run", fake_run)
    monkeypatch.setattr("local_n8n.core.backup.run_streaming", fake_run)
    monkeypatch.setattr("local_n8n.core.backup.wait_for_web_ui_ready", lambda url: True)

    restore_instance(bundle_path, secret="restore-secret")

    recovery_path = tmp_path / "instances" / "restored" / "recovery.wrapped"
    assert not recovery_path.exists()

    result = backup_instance(
        "restored",
        passphrase="new-passphrase",
        output_path=tmp_path / "after-restore.n8nbundle",
        recovery_code_factory=lambda: "new-recovery-code",
    )

    assert result.recovery_code == "new-recovery-code"
    assert recovery_path.exists()
    opened = open_bundle(result.bundle_path.read_bytes(), secret="new-recovery-code")
    assert _manifest_from_payload(opened.payload)["instance"] == "restored"


def test_restore_instance_refuses_existing_instance_without_replace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))
    _seed_instance(tmp_path)
    bundle_path = _write_restore_bundle(tmp_path, instance="default")

    with pytest.raises(Exception) as exc_info:
        restore_instance(bundle_path, secret="restore-secret")

    assert "already exists" in str(exc_info.value)


def test_restore_instance_replace_rolls_back_after_restore_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))
    _seed_instance(tmp_path)
    original_compose = (tmp_path / "instances" / "default" / "docker-compose.yml").read_bytes()
    original_env = (tmp_path / "instances" / "default" / ".env").read_bytes()
    bundle_path = _write_restore_bundle(tmp_path, instance="default")
    calls: list[list[str]] = []
    progress_messages: list[str] = []

    def fake_backup_instance(
        instance_name: str,
        *,
        passphrase: str,
        output_path: Path | None = None,
        progress: Any = None,
        recovery_code_factory: Any = None,
    ) -> BackupResult:
        assert instance_name == "default"
        assert passphrase == "restore-secret"
        assert output_path is not None
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"pre-restore")
        return BackupResult(
            instance="default",
            bundle_path=output_path,
            checksum="checksum",
            size=11,
            recovery_code=None,
            restarted=False,
        )

    def fake_run(args: list[str], cwd: Path) -> CommandResult:
        calls.append(args)
        if args[:2] == ["docker", "compose"] and "ps" in args:
            return CommandResult(args=args, returncode=0, stdout='[{"State":"running"}]', stderr="")
        return CommandResult(args=args, returncode=0, stdout="", stderr="")

    def fake_ready(url: str) -> bool:
        return url == "http://localhost:5678"

    monkeypatch.setattr("local_n8n.core.backup.backup_instance", fake_backup_instance)
    monkeypatch.setattr("local_n8n.core.backup.run", fake_run)
    monkeypatch.setattr("local_n8n.core.backup.run_streaming", fake_run)
    monkeypatch.setattr("local_n8n.core.backup.wait_for_web_ui_ready", fake_ready)

    with pytest.raises(Exception) as exc_info:
        restore_instance(
            bundle_path,
            secret="restore-secret",
            replace=True,
            port=5691,
            progress=progress_messages.append,
        )

    assert "did not become reachable" in str(exc_info.value)
    assert (
        tmp_path / "instances" / "default" / "docker-compose.yml"
    ).read_bytes() == original_compose
    assert (tmp_path / "instances" / "default" / ".env").read_bytes() == original_env
    with StateStore(tmp_path / "state.db") as state:
        record = state.get_instance("default")
    assert record is not None
    assert record.data_volume == "n8n_default_data"
    assert record.port == 5678
    assert any(command[:3] == ["docker", "volume", "rm"] for command in calls)
    assert any(command[-2:] == ["up", "-d"] for command in calls)
    assert "Rolling back failed replace restore..." in progress_messages


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


def _write_restore_bundle(tmp_path: Path, *, instance: str) -> Path:
    work_dir = tmp_path / "bundle-build"
    work_dir.mkdir(exist_ok=True)
    env_path = work_dir / ".env"
    compose_path = work_dir / "docker-compose.yml"
    volume_tar = work_dir / "volume.tar"
    env_path.write_text("N8N_ENCRYPTION_KEY=restored-key\nN8N_PORT=5678\n", encoding="utf-8")
    compose_path.write_text("services:\n  n8n: {}\n", encoding="utf-8")
    _write_volume_tar(volume_tar)
    manifest_path = work_dir / "manifest.json"
    manifest = {
        "bundle_schema": 1,
        "compose_schema": 1,
        "created_at": "2026-07-01T00:00:00Z",
        "db_type": "sqlite",
        "files": [
            _file_entry(".env", env_path),
            _file_entry("docker-compose.yml", compose_path),
            _file_entry("volume.tar", volume_tar),
        ],
        "image": "docker.n8n.io/n8nio/n8n",
        "instance": instance,
        "lon_version": "0.1.0a2",
        "n8n_version": None,
        "platform_created_on": "linux-wsl",
        "restore_policy": "same-version by default; --upgrade allows forward migration",
    }
    manifest_path.write_text(
        json.dumps(manifest, separators=(",", ":"), sort_keys=True), encoding="utf-8"
    )
    payload_path = work_dir / "payload.tar"
    with tarfile.open(payload_path, "w") as archive:
        archive.add(manifest_path, arcname="manifest.json")
        archive.add(volume_tar, arcname="volume.tar")
        archive.add(compose_path, arcname="docker-compose.yml")
        archive.add(env_path, arcname=".env")
    bundle_path = tmp_path / f"{instance}.n8nbundle"
    bundle_path.write_bytes(
        seal_bundle(
            payload_path.read_bytes(),
            passphrase="restore-secret",
            recovery_code="restore-recovery",
        )
    )
    return bundle_path


def _file_entry(name: str, path: Path) -> dict[str, object]:
    return {
        "path": name,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "size": path.stat().st_size,
    }
