from __future__ import annotations

import hashlib
import json
import platform
import secrets
import stat
import tarfile
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from local_n8n.compose.template import InstanceConfig, read_env_value, render_compose
from local_n8n.core.config import build_instance_config, config_home
from local_n8n.core.crypto import (
    BundleAuthenticationError,
    BundleFormatError,
    open_bundle,
    seal_bundle,
)
from local_n8n.core.errors import (
    CommandFailedError,
    InstanceNotFoundError,
    LonError,
    PrerequisiteError,
)
from local_n8n.core.readiness import wait_for_web_ui_ready
from local_n8n.core.runner import CommandResult, run, run_streaming
from local_n8n.core.state import BackupRecord, InstanceRecord, StateStore, utc_now

ProgressReporter = Callable[[str], None]
RecoveryCodeFactory = Callable[[], str]

HELPER_IMAGE = "docker.io/library/alpine:3.20"
BUNDLE_SCHEMA = 1
COMPOSE_SCHEMA = 1
PAYLOAD_MANIFEST = "manifest.json"
PAYLOAD_VOLUME_TAR = "volume.tar"
PAYLOAD_COMPOSE = "docker-compose.yml"
PAYLOAD_ENV = ".env"


@dataclass(frozen=True)
class BackupResult:
    instance: str
    bundle_path: Path
    checksum: str
    size: int
    recovery_code: str | None
    restarted: bool


@dataclass(frozen=True)
class RestoreResult:
    instance: str
    url: str
    compose_path: Path
    env_path: Path
    volume_name: str
    replaced: bool
    pre_restore_backup: Path | None


@dataclass(frozen=True)
class _ReplaceRollbackContext:
    record: InstanceRecord
    config: InstanceConfig
    compose_bytes: bytes
    env_bytes: bytes
    was_running: bool


def backup_instance(
    instance_name: str,
    *,
    passphrase: str,
    output_path: Path | None = None,
    progress: ProgressReporter | None = None,
    recovery_code_factory: RecoveryCodeFactory | None = None,
) -> BackupResult:
    with StateStore.open_default() as state:
        record = state.get_instance(instance_name)
        if record is None:
            raise InstanceNotFoundError(
                f"Instance {instance_name!r} is not registered.",
                hint="Run `lon init` first to create it.",
            )

    config = build_instance_config(
        record.name,
        record.port,
        data_volume=record.data_volume,
        image_ref=record.image_ref,
    )
    if not config.compose_path.exists() or not config.env_path.exists():
        raise LonError(
            f"Instance {instance_name!r} is missing compose or environment files.",
            hint=f"Expected files under {config.instance_dir}.",
        )

    created_at = utc_now()
    bundle_path = output_path or _default_bundle_path(record.name, created_at)
    bundle_path.parent.mkdir(parents=True, exist_ok=True)
    recovery_code, generated_recovery_code = _load_or_create_recovery_code(
        config.instance_dir,
        passphrase=passphrase,
        recovery_code_factory=recovery_code_factory or _generate_recovery_code,
    )
    was_running = _container_is_running(
        config.instance_dir,
        _compose_args(config, "ps", "--all", "--format", "json"),
    )
    restarted = False

    try:
        if was_running:
            _report(progress, "Stopping n8n for a consistent backup...")
            _run_docker(config.instance_dir, _compose_args(config, "stop", "n8n"), stream=True)

        _report(progress, "Capturing n8n Docker volume...")
        with tempfile.TemporaryDirectory(prefix="local-n8n-backup-") as temp_dir:
            work_dir = Path(temp_dir)
            volume_tar = work_dir / PAYLOAD_VOLUME_TAR
            _capture_volume(record.data_volume, volume_tar)
            _report(progress, "Building encrypted backup bundle...")
            payload = _build_payload(
                record=record,
                compose_path=config.compose_path,
                env_path=config.env_path,
                volume_tar=volume_tar,
                created_at=created_at,
            )

        bundle = seal_bundle(payload, passphrase=passphrase, recovery_code=recovery_code)
        bundle_path.write_bytes(bundle)
        checksum = _sha256_bytes(bundle)
        size = len(bundle)
        with StateStore.open_default() as state:
            state.record_backup(
                BackupRecord(
                    instance=record.name,
                    created_at=created_at,
                    location=bundle_path,
                    checksum=checksum,
                    size=size,
                    n8n_version=record.n8n_version,
                )
            )
    finally:
        if was_running:
            _report(progress, "Restarting n8n after backup...")
            _run_docker(config.instance_dir, _compose_args(config, "start", "n8n"), stream=True)
            restarted = True
            url = f"http://localhost:{record.port}"
            _report(progress, "Waiting for n8n web UI...")
            if not wait_for_web_ui_ready(url):
                raise LonError(
                    "Backup finished, but n8n did not become reachable after restart.",
                    hint=f"Check Docker logs, then try opening {url}.",
                )

    return BackupResult(
        instance=record.name,
        bundle_path=bundle_path,
        checksum=checksum,
        size=size,
        recovery_code=generated_recovery_code,
        restarted=restarted,
    )


def restore_instance(
    bundle_path: Path,
    *,
    secret: str,
    replace: bool = False,
    port: int | None = None,
    progress: ProgressReporter | None = None,
) -> RestoreResult:
    if not bundle_path.exists():
        raise LonError(f"Backup bundle does not exist: {bundle_path}")

    _report(progress, "Decrypting backup bundle...")
    try:
        opened = open_bundle(bundle_path.read_bytes(), secret=secret)
    except (BundleAuthenticationError, BundleFormatError) as exc:
        raise LonError(
            "Could not open backup bundle.",
            hint="Check the backup passphrase or recovery code.",
        ) from exc

    with tempfile.TemporaryDirectory(prefix="local-n8n-restore-") as temp_dir:
        work_dir = Path(temp_dir)
        payload_files = _unpack_payload(opened.payload, work_dir)
        manifest = _load_manifest(payload_files[PAYLOAD_MANIFEST])
        _validate_manifest(manifest, payload_files)
        instance_name = _manifest_string(manifest, "instance")
        image_ref = _manifest_string(manifest, "image")

        with StateStore.open_default() as state:
            existing = state.get_instance(instance_name)
        if existing is not None and not replace:
            raise LonError(
                f"Instance {instance_name!r} already exists.",
                hint="Use `lon restore --replace` to replace it after making a safety backup.",
            )

        pre_restore_backup: Path | None = None
        rollback: _ReplaceRollbackContext | None = None
        restored_config: InstanceConfig | None = None
        restored_volume: str | None = None
        try:
            if existing is not None:
                pre_restore_backup = _pre_restore_backup_path(instance_name)
                _report(progress, "Creating pre-restore safety backup...")
                backup_instance(
                    instance_name,
                    passphrase=secret,
                    output_path=pre_restore_backup,
                    progress=progress,
                )
                existing_config = build_instance_config(
                    existing.name,
                    existing.port,
                    data_volume=existing.data_volume,
                    image_ref=existing.image_ref,
                )
                rollback = _replace_rollback_context(existing, existing_config)
                _report(progress, "Stopping existing instance before restore...")
                _run_docker(
                    existing_config.instance_dir,
                    _compose_args(existing_config, "down"),
                    stream=True,
                )

            restored_port = port or _port_from_env_file(payload_files[PAYLOAD_ENV]) or 5678
            volume_name = _restored_volume_name(instance_name)
            restored_volume = volume_name
            config = build_instance_config(
                instance_name,
                restored_port,
                data_volume=volume_name,
                image_ref=image_ref,
            )
            restored_config = config
            _report(progress, "Restoring instance files...")
            config.instance_dir.mkdir(parents=True, exist_ok=True)
            config.env_path.write_bytes(payload_files[PAYLOAD_ENV].read_bytes())
            _set_env_port(config.env_path, restored_port)
            config.env_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
            config.compose_path.write_text(render_compose(config), encoding="utf-8")

            _report(progress, "Restoring n8n Docker volume...")
            _restore_volume(volume_name, payload_files[PAYLOAD_VOLUME_TAR])

            with StateStore.open_default() as state:
                state.upsert_instance(
                    InstanceRecord(
                        name=instance_name,
                        compose_path=config.compose_path,
                        data_volume=volume_name,
                        port=restored_port,
                        image_ref=image_ref,
                        enc_key_ref=config.env_path,
                        created_at=utc_now(),
                        db_type=_manifest_string(manifest, "db_type"),
                        n8n_version=_manifest_optional_string(manifest, "n8n_version"),
                    )
                )

            _report(progress, "Starting restored n8n instance...")
            _run_docker(config.instance_dir, _compose_args(config, "up", "-d"), stream=True)
            url = f"http://localhost:{restored_port}"
            _report(progress, "Waiting for n8n web UI...")
            if not wait_for_web_ui_ready(url):
                raise LonError(
                    "Restored n8n started, but the web UI did not become reachable in time.",
                    hint=f"Check Docker logs, then try opening {url}.",
                )
        except Exception as exc:
            if rollback is not None:
                rollback_error = _rollback_replace_restore(
                    rollback,
                    restored_config=restored_config,
                    restored_volume=restored_volume,
                    progress=progress,
                )
                if rollback_error is not None:
                    raise LonError(
                        "Restore failed and rollback also failed.",
                        hint=f"Original failure: {exc}. Rollback failure: {rollback_error}.",
                    ) from exc
            raise

        return RestoreResult(
            instance=instance_name,
            url=url,
            compose_path=config.compose_path,
            env_path=config.env_path,
            volume_name=volume_name,
            replaced=existing is not None,
            pre_restore_backup=pre_restore_backup,
        )


def reveal_recovery_code(instance_name: str, *, passphrase: str) -> str:
    with StateStore.open_default() as state:
        record = state.get_instance(instance_name)
        if record is None:
            raise InstanceNotFoundError(
                f"Instance {instance_name!r} is not registered.",
                hint="Run `lon init` first to create it.",
            )

    config = build_instance_config(
        record.name,
        record.port,
        data_volume=record.data_volume,
        image_ref=record.image_ref,
    )
    recovery_path = config.instance_dir / "recovery.wrapped"
    if not recovery_path.exists():
        raise LonError(
            f"Recovery material for instance {instance_name!r} does not exist.",
            hint="Run `lon backup` first to create and display a recovery code.",
        )

    try:
        opened = open_bundle(
            recovery_path.read_bytes(),
            secret=passphrase,
            slot_type="passphrase",
        )
    except (BundleAuthenticationError, BundleFormatError) as exc:
        raise LonError(
            "Could not unlock recovery material.",
            hint="Use the passphrase that was used when backups were first enabled.",
        ) from exc
    return opened.payload.decode("utf-8")


def _replace_rollback_context(
    record: InstanceRecord,
    config: InstanceConfig,
) -> _ReplaceRollbackContext:
    return _ReplaceRollbackContext(
        record=record,
        config=config,
        compose_bytes=config.compose_path.read_bytes(),
        env_bytes=config.env_path.read_bytes(),
        was_running=_container_is_running(
            config.instance_dir,
            _compose_args(config, "ps", "--all", "--format", "json"),
        ),
    )


def _rollback_replace_restore(
    rollback: _ReplaceRollbackContext,
    *,
    restored_config: InstanceConfig | None,
    restored_volume: str | None,
    progress: ProgressReporter | None,
) -> str | None:
    try:
        _report(progress, "Rolling back failed replace restore...")
        if restored_config is not None and restored_config.compose_path.exists():
            _run_docker(
                restored_config.instance_dir,
                _compose_args(restored_config, "down"),
                stream=True,
            )
        if restored_volume is not None and restored_volume != rollback.record.data_volume:
            _run_docker(
                rollback.config.instance_dir,
                ["docker", "volume", "rm", "--force", restored_volume],
                stream=True,
            )

        rollback.config.instance_dir.mkdir(parents=True, exist_ok=True)
        rollback.config.compose_path.write_bytes(rollback.compose_bytes)
        rollback.config.env_path.write_bytes(rollback.env_bytes)
        rollback.config.env_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
        with StateStore.open_default() as state:
            state.upsert_instance(rollback.record)

        if rollback.was_running:
            _report(progress, "Restarting previous instance after rollback...")
            _run_docker(
                rollback.config.instance_dir,
                _compose_args(rollback.config, "up", "-d"),
                stream=True,
            )
            url = f"http://localhost:{rollback.record.port}"
            _report(progress, "Waiting for previous n8n web UI...")
            if not wait_for_web_ui_ready(url):
                raise LonError(
                    "Rollback restored the previous instance, "
                    "but its web UI did not become reachable.",
                    hint=f"Check Docker logs, then try opening {url}.",
                )
    except Exception as exc:
        return str(exc)
    return None


def _load_or_create_recovery_code(
    instance_dir: Path,
    *,
    passphrase: str,
    recovery_code_factory: RecoveryCodeFactory,
) -> tuple[str, str | None]:
    recovery_path = instance_dir / "recovery.wrapped"
    if recovery_path.exists():
        try:
            opened = open_bundle(
                recovery_path.read_bytes(),
                secret=passphrase,
                slot_type="passphrase",
            )
        except (BundleAuthenticationError, BundleFormatError) as exc:
            raise LonError(
                "Could not unlock existing recovery material.",
                hint="Use the passphrase that was used when backups were first enabled.",
            ) from exc
        return opened.payload.decode("utf-8"), None

    recovery_code = recovery_code_factory()
    recovery_path.write_bytes(
        seal_bundle(
            recovery_code.encode("utf-8"),
            passphrase=passphrase,
            recovery_code=recovery_code,
        )
    )
    recovery_path.chmod(0o600)
    return recovery_code, recovery_code


def _build_payload(
    *,
    record: InstanceRecord,
    compose_path: Path,
    env_path: Path,
    volume_tar: Path,
    created_at: str,
) -> bytes:
    manifest = _build_manifest(
        record=record,
        created_at=created_at,
        files={
            PAYLOAD_VOLUME_TAR: volume_tar,
            PAYLOAD_COMPOSE: compose_path,
            PAYLOAD_ENV: env_path,
        },
    )
    with tempfile.TemporaryDirectory(prefix="local-n8n-payload-") as temp_dir:
        payload_path = Path(temp_dir) / "payload.tar"
        manifest_path = Path(temp_dir) / PAYLOAD_MANIFEST
        manifest_path.write_text(_canonical_json(manifest), encoding="utf-8")
        with tarfile.open(payload_path, "w") as archive:
            archive.add(manifest_path, arcname=PAYLOAD_MANIFEST)
            archive.add(volume_tar, arcname=PAYLOAD_VOLUME_TAR)
            archive.add(compose_path, arcname=PAYLOAD_COMPOSE)
            archive.add(env_path, arcname=PAYLOAD_ENV)
        return payload_path.read_bytes()


def _build_manifest(
    *,
    record: InstanceRecord,
    created_at: str,
    files: dict[str, Path],
) -> dict[str, object]:
    return {
        "bundle_schema": BUNDLE_SCHEMA,
        "compose_schema": COMPOSE_SCHEMA,
        "created_at": created_at,
        "db_type": record.db_type,
        "files": [
            {
                "path": path,
                "sha256": _sha256_file(file_path),
                "size": file_path.stat().st_size,
            }
            for path, file_path in sorted(files.items())
        ],
        "image": record.image_ref,
        "instance": record.name,
        "lon_version": _lon_version(),
        "n8n_version": record.n8n_version,
        "platform_created_on": _platform_created_on(),
        "restore_policy": "same-version by default; --upgrade allows forward migration",
    }


def _capture_volume(volume_name: str, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result = _run_docker(
        output_path.parent,
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{volume_name}:/volume:ro",
            "-v",
            f"{output_path.parent}:/backup",
            HELPER_IMAGE,
            "tar",
            "--numeric-owner",
            "-C",
            "/volume",
            "-cf",
            f"/backup/{output_path.name}",
            ".",
        ],
        stream=True,
    )
    if result.returncode != 0:
        raise CommandFailedError("Could not capture n8n Docker volume.", hint=result.stderr)


def _restore_volume(volume_name: str, volume_tar: Path) -> None:
    _run_docker(volume_tar.parent, ["docker", "volume", "create", volume_name], stream=True)
    _run_docker(
        volume_tar.parent,
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{volume_name}:/volume",
            "-v",
            f"{volume_tar.parent}:/backup",
            HELPER_IMAGE,
            "tar",
            "--numeric-owner",
            "-C",
            "/volume",
            "-xf",
            f"/backup/{volume_tar.name}",
        ],
        stream=True,
    )


def _unpack_payload(payload: bytes, work_dir: Path) -> dict[str, Path]:
    payload_path = work_dir / "payload.tar"
    payload_path.write_bytes(payload)
    extracted: dict[str, Path] = {}
    with tarfile.open(payload_path, "r") as archive:
        for name in [PAYLOAD_MANIFEST, PAYLOAD_VOLUME_TAR, PAYLOAD_COMPOSE, PAYLOAD_ENV]:
            member = archive.extractfile(name)
            if member is None:
                raise LonError(f"Backup payload is missing {name}.")
            target = work_dir / name
            target.write_bytes(member.read())
            extracted[name] = target
    return extracted


def _load_manifest(path: Path) -> dict[str, object]:
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise LonError("Backup manifest is not valid JSON.") from exc
    if not isinstance(parsed, dict):
        raise LonError("Backup manifest must be a JSON object.")
    return parsed


def _validate_manifest(manifest: dict[str, object], files: dict[str, Path]) -> None:
    if manifest.get("bundle_schema") != BUNDLE_SCHEMA:
        raise LonError("Backup bundle schema is not supported.")
    if manifest.get("compose_schema") != COMPOSE_SCHEMA:
        raise LonError("Backup compose schema is not supported.")
    expected_files = manifest.get("files")
    if not isinstance(expected_files, list):
        raise LonError("Backup manifest does not list files.")
    by_path: dict[str, dict[str, object]] = {}
    for item in expected_files:
        if not isinstance(item, dict):
            raise LonError("Backup manifest file entry is invalid.")
        path = item.get("path")
        if isinstance(path, str):
            by_path[path] = cast(dict[str, object], item)
    for name in [PAYLOAD_VOLUME_TAR, PAYLOAD_COMPOSE, PAYLOAD_ENV]:
        entry = by_path.get(name)
        if entry is None:
            raise LonError(f"Backup manifest is missing file metadata for {name}.")
        actual = files[name]
        if entry.get("sha256") != _sha256_file(actual):
            raise LonError(f"Backup payload file failed checksum verification: {name}.")
        if entry.get("size") != actual.stat().st_size:
            raise LonError(f"Backup payload file size mismatch: {name}.")
    _manifest_string(manifest, "instance")
    _manifest_string(manifest, "image")
    _manifest_string(manifest, "db_type")


def _manifest_string(manifest: dict[str, object], key: str) -> str:
    value = manifest.get(key)
    if not isinstance(value, str) or not value:
        raise LonError(f"Backup manifest field {key!r} is missing or invalid.")
    return value


def _manifest_optional_string(manifest: dict[str, object], key: str) -> str | None:
    value = manifest.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise LonError(f"Backup manifest field {key!r} is invalid.")
    return value


def _port_from_env_file(path: Path) -> int | None:
    raw_port = read_env_value(path, "N8N_PORT")
    if raw_port is None:
        return None
    try:
        return int(raw_port)
    except ValueError:
        return None


def _set_env_port(path: Path, port: int) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    replaced = False
    output: list[str] = []
    for line in lines:
        if line.startswith("N8N_PORT="):
            output.append(f"N8N_PORT={port}")
            replaced = True
        else:
            output.append(line)
    if not replaced:
        output.append(f"N8N_PORT={port}")
    path.write_text("\n".join(output) + "\n", encoding="utf-8")


def _restored_volume_name(instance_name: str) -> str:
    return f"n8n_{instance_name}_data.g{utc_now().replace(':', '-').replace('.', '-')}"


def _pre_restore_backup_path(instance_name: str) -> Path:
    safe_created_at = utc_now().replace(":", "-")
    return config_home() / "backups" / f"{instance_name}-pre-restore-{safe_created_at}.n8nbundle"


def _container_is_running(cwd: Path, command: list[str]) -> bool:
    result = _run_docker(cwd, command)
    if not result.stdout.strip():
        return False
    try:
        parsed = json.loads(result.stdout)
    except json.JSONDecodeError:
        return "running" in result.stdout.lower()
    rows = parsed if isinstance(parsed, list) else [parsed]
    for row in rows:
        if isinstance(row, dict) and str(row.get("State", "")).lower() == "running":
            return True
    return False


def _compose_args(config: InstanceConfig, *args: str) -> list[str]:
    return ["docker", "compose", "-p", config.project_name, "-f", str(config.compose_path), *args]


def _run_docker(cwd: Path, command: list[str], stream: bool = False) -> CommandResult:
    try:
        runner = run_streaming if stream else run
        result = runner(command, cwd=cwd)
    except FileNotFoundError as exc:
        raise PrerequisiteError(
            "Docker was not found.",
            hint="Install Docker, then retry.",
        ) from exc

    if result.returncode != 0:
        raise CommandFailedError(
            "Docker command failed during backup.",
            hint=(
                result.stderr.strip() or result.stdout.strip() or "Run again with Docker available."
            ),
        )
    return result


def _default_bundle_path(instance_name: str, created_at: str) -> Path:
    safe_created_at = created_at.replace(":", "-")
    return config_home() / "backups" / f"{instance_name}-{safe_created_at}.n8nbundle"


def _canonical_json(value: object) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _platform_created_on() -> str:
    system = platform.system().lower()
    if system == "linux" and _is_wsl():
        return "linux-wsl"
    if system == "darwin":
        return "macos"
    return system


def _is_wsl() -> bool:
    osrelease = Path("/proc/sys/kernel/osrelease")
    if not osrelease.exists():
        return False
    try:
        return "microsoft" in osrelease.read_text(encoding="utf-8").lower()
    except OSError:
        return False


def _lon_version() -> str:
    from local_n8n import __version__

    return __version__


def _generate_recovery_code() -> str:
    return secrets.token_urlsafe(32)


def _report(progress: ProgressReporter | None, message: str) -> None:
    if progress is not None:
        progress(message)
