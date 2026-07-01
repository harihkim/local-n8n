from __future__ import annotations

import json
import platform
from dataclasses import dataclass
from pathlib import Path

from local_n8n.compose.template import (
    DEFAULT_IMAGE_REF,
    InstanceConfig,
    ensure_instance_files,
    read_env_value,
)
from local_n8n.core.config import build_instance_config
from local_n8n.core.errors import (
    CommandFailedError,
    InstanceNotFoundError,
    LonError,
    PortInUseError,
    PrerequisiteError,
    StartupTimeoutError,
)
from local_n8n.core.readiness import wait_for_http_ready
from local_n8n.core.runner import CommandResult, run
from local_n8n.core.state import InstanceRecord, StateStore, new_instance_record, utc_now

CONTAINER_NOT_PRESENT = "not present"


@dataclass(frozen=True)
class UpResult:
    url: str
    compose_path: Path
    volume_name: str


@dataclass(frozen=True)
class DownResult:
    volume_name: str


@dataclass(frozen=True)
class StopResult:
    volume_name: str


@dataclass(frozen=True)
class StartResult:
    url: str


@dataclass(frozen=True)
class StatusResult:
    name: str
    url: str
    compose_path: Path
    volume_name: str
    container_state: str
    health: str | None = None


@dataclass(frozen=True)
class InstanceListItem:
    name: str
    url: str
    container_state: str
    volume_name: str


@dataclass(frozen=True)
class LogsResult:
    output: str


@dataclass(frozen=True)
class RestartResult:
    url: str


@dataclass(frozen=True)
class OpenResult:
    url: str
    opened: bool
    opener: str | None = None


def up_instance(instance_name: str, port: int | None = None) -> UpResult:
    with StateStore.open_default() as state:
        record = _get_or_adopt_instance(state, instance_name, port, allow_create=True)
        effective_port = port or record.port
        config = build_instance_config(
            instance_name,
            effective_port,
            data_volume=record.data_volume,
            image_ref=record.image_ref,
        )
        ensure_instance_files(config)
        state.upsert_instance(
            InstanceRecord(
                name=record.name,
                compose_path=config.compose_path,
                data_volume=config.volume_name,
                port=effective_port,
                base_url=record.base_url,
                db_type=record.db_type,
                image_ref=config.image_ref,
                n8n_version=record.n8n_version,
                enc_key_ref=config.env_path,
                created_at=record.created_at,
                last_started_at=record.last_started_at,
            )
        )
        url = f"http://localhost:{effective_port}"

        _run_compose(
            config.instance_dir,
            [
                "docker",
                "compose",
                "-p",
                config.project_name,
                "-f",
                str(config.compose_path),
                "up",
                "-d",
            ],
        )

        if not wait_for_http_ready(url):
            raise StartupTimeoutError(
                "n8n started, but the editor did not become reachable in time.",
                hint=f"Check Docker logs, then try opening {url} again.",
            )

        state.record_started(instance_name)

        return UpResult(
            url=url,
            compose_path=config.compose_path,
            volume_name=config.volume_name,
        )


def down_instance(instance_name: str) -> DownResult:
    with StateStore.open_default() as state:
        record = _get_or_adopt_instance(state, instance_name)
    config = build_instance_config(
        instance_name,
        record.port,
        data_volume=record.data_volume,
        image_ref=record.image_ref,
    )
    _run_compose(
        config.instance_dir,
        [
            "docker",
            "compose",
            "-p",
            config.project_name,
            "-f",
            str(config.compose_path),
            "down",
        ],
    )
    return DownResult(volume_name=config.volume_name)


def stop_instance(instance_name: str) -> StopResult:
    with StateStore.open_default() as state:
        record = _get_or_adopt_instance(state, instance_name)
    config = build_instance_config(
        instance_name,
        record.port,
        data_volume=record.data_volume,
        image_ref=record.image_ref,
    )
    _run_compose(
        config.instance_dir,
        [
            "docker",
            "compose",
            "-p",
            config.project_name,
            "-f",
            str(config.compose_path),
            "stop",
        ],
    )
    return StopResult(volume_name=config.volume_name)


def start_instance(instance_name: str) -> StartResult:
    with StateStore.open_default() as state:
        record = _get_or_adopt_instance(state, instance_name)
    config = build_instance_config(
        instance_name,
        record.port,
        data_volume=record.data_volume,
        image_ref=record.image_ref,
    )
    url = f"http://localhost:{record.port}"
    container_state, _health = _compose_container_status(config)
    if container_state == CONTAINER_NOT_PRESENT:
        raise LonError(
            f"Instance {instance_name!r} is down; there is no container to start.",
            hint=f"Run `lon up --instance {instance_name}` to create and start it.",
        )

    _run_compose(
        config.instance_dir,
        [
            "docker",
            "compose",
            "-p",
            config.project_name,
            "-f",
            str(config.compose_path),
            "start",
        ],
    )
    if not wait_for_http_ready(url):
        raise StartupTimeoutError(
            "n8n started, but the editor did not become reachable in time.",
            hint=f"Check Docker logs, then try opening {url} again.",
        )
    return StartResult(url=url)


def restart_instance(instance_name: str) -> RestartResult:
    with StateStore.open_default() as state:
        record = _get_or_adopt_instance(state, instance_name)
    config = build_instance_config(
        instance_name,
        record.port,
        data_volume=record.data_volume,
        image_ref=record.image_ref,
    )
    url = f"http://localhost:{record.port}"
    container_state, _health = _compose_container_status(config)
    if container_state == CONTAINER_NOT_PRESENT:
        raise LonError(
            f"Instance {instance_name!r} is down; there is no container to restart.",
            hint=f"Run `lon up --instance {instance_name}` to create and start it.",
        )

    _run_compose(
        config.instance_dir,
        [
            "docker",
            "compose",
            "-p",
            config.project_name,
            "-f",
            str(config.compose_path),
            "restart",
        ],
    )
    if not wait_for_http_ready(url):
        raise StartupTimeoutError(
            "n8n restarted, but the editor did not become reachable in time.",
            hint=f"Check Docker logs, then try opening {url} again.",
        )
    return RestartResult(url=url)


def status_instance(instance_name: str) -> StatusResult:
    with StateStore.open_default() as state:
        record = _get_or_adopt_instance(state, instance_name)
    config = build_instance_config(
        instance_name,
        record.port,
        data_volume=record.data_volume,
        image_ref=record.image_ref,
    )
    container_state, health = _compose_container_status(config)
    return StatusResult(
        name=record.name,
        url=f"http://localhost:{record.port}",
        compose_path=config.compose_path,
        volume_name=config.volume_name,
        container_state=container_state,
        health=health,
    )


def list_instances() -> list[InstanceListItem]:
    with StateStore.open_default() as state:
        records = state.list_instances()

    items: list[InstanceListItem] = []
    for record in records:
        config = build_instance_config(
            record.name,
            record.port,
            data_volume=record.data_volume,
            image_ref=record.image_ref,
        )
        container_state, _health = _compose_container_status(config)
        items.append(
            InstanceListItem(
                name=record.name,
                url=f"http://localhost:{record.port}",
                container_state=container_state,
                volume_name=config.volume_name,
            )
        )

    return items


def logs_instance(instance_name: str, follow: bool = False, tail: int = 100) -> LogsResult:
    with StateStore.open_default() as state:
        record = _get_or_adopt_instance(state, instance_name)
    config = build_instance_config(
        instance_name,
        record.port,
        data_volume=record.data_volume,
        image_ref=record.image_ref,
    )
    command = [
        "docker",
        "compose",
        "-p",
        config.project_name,
        "-f",
        str(config.compose_path),
        "logs",
        f"--tail={tail}",
    ]
    if follow:
        command.append("-f")
    result = _run_compose(config.instance_dir, command)
    return LogsResult(output=result.stdout)


def open_instance(instance_name: str) -> OpenResult:
    with StateStore.open_default() as state:
        record = _get_or_adopt_instance(state, instance_name)
    url = f"http://localhost:{record.port}"
    for opener in _open_commands(url):
        try:
            result = run(opener, cwd=Path.cwd())
        except FileNotFoundError:
            continue
        if result.returncode == 0:
            return OpenResult(url=url, opened=True, opener=opener[0])
    return OpenResult(url=url, opened=False)


def _get_or_adopt_instance(
    state: StateStore,
    instance_name: str,
    requested_port: int | None = None,
    allow_create: bool = False,
) -> InstanceRecord:
    existing = state.get_instance(instance_name)
    if existing is not None:
        return existing

    config = build_instance_config(instance_name, requested_port or 5678)
    env_port = _read_port_from_env(config.env_path)
    if not allow_create and not config.compose_path.exists() and not config.env_path.exists():
        raise InstanceNotFoundError(
            f"Instance {instance_name!r} is not registered.",
            hint="Run `lon up` first to create it.",
        )

    port = requested_port or env_port or config.port
    adopted_config = build_instance_config(instance_name, port)
    record = new_instance_record(
        name=instance_name,
        compose_path=adopted_config.compose_path,
        data_volume=adopted_config.volume_name,
        port=port,
        image_ref=DEFAULT_IMAGE_REF,
        enc_key_ref=adopted_config.env_path,
        created_at=utc_now(),
    )
    state.upsert_instance(record)
    return record


def _read_port_from_env(env_path: Path) -> int | None:
    raw_port = read_env_value(env_path, "N8N_PORT")
    if raw_port is None:
        return None

    try:
        return int(raw_port)
    except ValueError:
        return None


def _parse_compose_ps(output: str) -> tuple[str, str | None]:
    stripped = output.strip()
    if not stripped:
        return (CONTAINER_NOT_PRESENT, None)

    rows: list[object]
    try:
        parsed = json.loads(stripped)
        rows = parsed if isinstance(parsed, list) else [parsed]
    except json.JSONDecodeError:
        rows = [json.loads(line) for line in stripped.splitlines() if line.strip()]

    if not rows:
        return (CONTAINER_NOT_PRESENT, None)

    first = rows[0]
    if not isinstance(first, dict):
        return ("unknown", None)

    state = str(first.get("State") or first.get("Status") or "unknown")
    health = first.get("Health")
    return (state, str(health) if health is not None else None)


def _compose_container_status(config: InstanceConfig) -> tuple[str, str | None]:
    result = _run_compose(
        config.instance_dir,
        [
            "docker",
            "compose",
            "-p",
            config.project_name,
            "-f",
            str(config.compose_path),
            "ps",
            "--format",
            "json",
        ],
    )
    return _parse_compose_ps(result.stdout)


def _open_commands(url: str) -> list[list[str]]:
    if _is_wsl():
        return [["wslview", url], ["powershell.exe", "Start-Process", url]]
    if platform.system() == "Darwin":
        return [["open", url]]
    return [["xdg-open", url]]


def _is_wsl() -> bool:
    osrelease = Path("/proc/sys/kernel/osrelease")
    if not osrelease.exists():
        return False
    try:
        return "microsoft" in osrelease.read_text(encoding="utf-8").lower()
    except OSError:
        return False


def _run_compose(cwd: Path, command: list[str]) -> CommandResult:
    try:
        result = run(command, cwd=cwd)
    except FileNotFoundError as exc:
        raise PrerequisiteError(
            "Docker was not found.",
            hint="Install Docker Engine inside WSL/Linux, then re-run this command.",
        ) from exc

    if result.returncode == 0:
        return result

    stderr = result.stderr.lower()
    stdout = result.stdout.lower()
    output = f"{stderr}\n{stdout}"

    if "cannot connect to the docker daemon" in output or "docker daemon is not running" in output:
        raise PrerequisiteError(
            "Docker is installed, but the daemon is not running.",
            hint="Start Docker Engine in WSL/Linux, then re-run this command.",
        )

    if (
        "port is already allocated" in output
        or "address already in use" in output
        or "ports are not available" in output
    ):
        raise PortInUseError(
            "Port 5678 is already in use.",
            hint="Stop the process using the port, or run with a different --port.",
        )

    raise CommandFailedError(
        "Docker Compose failed.",
        hint=(
            result.stderr.strip()
            or result.stdout.strip()
            or "Run again with Docker output available."
        ),
    )
