from __future__ import annotations

import hashlib
import json
import platform
import secrets
import tarfile
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from local_n8n.compose.template import InstanceConfig
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
