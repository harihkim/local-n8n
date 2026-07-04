from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from local_n8n.compose.template import read_env_value
from local_n8n.core.config import build_instance_config, config_home
from local_n8n.core.doctor import DoctorCheck, DoctorReport, run_doctor
from local_n8n.core.errors import LonError, PortInUseError, PrerequisiteError
from local_n8n.core.instance import open_instance, up_instance
from local_n8n.core.state import InstanceRecord, StateStore

ProgressReporter = Callable[[str], None]


class InitState(StrEnum):
    NEW = "new"
    ADOPTABLE = "adoptable"
    INITIALIZED = "initialized"


class InitStep(StrEnum):
    CHECK_PREREQUISITES = "check_prerequisites"
    ENSURE_INSTANCE_FILES = "ensure_instance_files"
    REGISTER_INSTANCE = "register_instance"
    START_INSTANCE = "start_instance"
    OPEN_WEB_UI = "open_web_ui"
    EXPLAIN_OWNER_SETUP = "explain_owner_setup"


@dataclass(frozen=True)
class InitPlan:
    instance_name: str
    requested_port: int | None
    port: int
    url: str
    state: InitState
    compose_path: Path
    env_path: Path
    volume_name: str
    image_ref: str
    registered: bool
    compose_exists: bool
    env_exists: bool
    will_create_compose: bool
    will_create_env: bool
    will_preserve_env: bool
    will_register: bool
    will_start: bool
    will_open: bool
    requested_port_ignored: bool
    steps: tuple[InitStep, ...]


@dataclass(frozen=True)
class InitResult:
    plan: InitPlan
    started: bool
    opened: bool
    opener: str | None = None


def init_instance(
    instance_name: str = "default",
    port: int | None = None,
    open_browser: bool = True,
    progress: ProgressReporter | None = None,
) -> InitResult:
    plan = plan_init(instance_name=instance_name, port=port, open_browser=open_browser)
    _report(progress, f"Preparing local-n8n instance {plan.instance_name!r}...")
    if plan.requested_port_ignored:
        _report(
            progress,
            (
                f"Instance already uses port {plan.port}; "
                f"ignoring requested port {plan.requested_port}."
            ),
        )

    _report(progress, "Checking Docker prerequisites...")
    _raise_if_prerequisites_fail(run_doctor(port=plan.port, check_port=False))
    _report(progress, "Docker prerequisites look ready.")

    up_instance(instance_name=plan.instance_name, port=plan.port, progress=progress)

    opened = False
    opener = None
    if plan.will_open:
        _report(progress, "Opening n8n web UI...")
        open_result = open_instance(plan.instance_name)
        opened = open_result.opened
        opener = open_result.opener

    return InitResult(
        plan=plan,
        started=True,
        opened=opened,
        opener=opener,
    )


def plan_init(
    instance_name: str = "default",
    port: int | None = None,
    open_browser: bool = True,
) -> InitPlan:
    base_config = build_instance_config(instance_name, port or 5678)
    record = _load_registered_instance(instance_name)
    if record is not None:
        return _registered_plan(record, requested_port=port, open_browser=open_browser)

    env_port = _read_port_from_env(base_config.env_path)
    effective_port = port or env_port or base_config.port
    config = build_instance_config(instance_name, effective_port)
    compose_exists = config.compose_path.exists()
    env_exists = config.env_path.exists()
    state = InitState.ADOPTABLE if compose_exists or env_exists else InitState.NEW

    return _build_plan(
        instance_name=instance_name,
        requested_port=port,
        port=effective_port,
        state=state,
        compose_path=config.compose_path,
        env_path=config.env_path,
        volume_name=config.volume_name,
        image_ref=config.image_ref,
        registered=False,
        compose_exists=compose_exists,
        env_exists=env_exists,
        will_register=True,
        will_open=open_browser,
        requested_port_ignored=False,
    )


def _registered_plan(
    record: InstanceRecord,
    requested_port: int | None,
    open_browser: bool,
) -> InitPlan:
    compose_exists = record.compose_path.exists()
    env_exists = record.enc_key_ref.exists()
    requested_port_ignored = requested_port is not None and requested_port != record.port
    return _build_plan(
        instance_name=record.name,
        requested_port=requested_port,
        port=record.port,
        state=InitState.INITIALIZED,
        compose_path=record.compose_path,
        env_path=record.enc_key_ref,
        volume_name=record.data_volume,
        image_ref=record.image_ref,
        registered=True,
        compose_exists=compose_exists,
        env_exists=env_exists,
        will_register=False,
        will_open=open_browser,
        requested_port_ignored=requested_port_ignored,
    )


def _build_plan(
    *,
    instance_name: str,
    requested_port: int | None,
    port: int,
    state: InitState,
    compose_path: Path,
    env_path: Path,
    volume_name: str,
    image_ref: str,
    registered: bool,
    compose_exists: bool,
    env_exists: bool,
    will_register: bool,
    will_open: bool,
    requested_port_ignored: bool,
) -> InitPlan:
    steps = [
        InitStep.CHECK_PREREQUISITES,
        InitStep.ENSURE_INSTANCE_FILES,
    ]
    if will_register:
        steps.append(InitStep.REGISTER_INSTANCE)
    steps.append(InitStep.START_INSTANCE)
    if will_open:
        steps.append(InitStep.OPEN_WEB_UI)
    steps.append(InitStep.EXPLAIN_OWNER_SETUP)

    return InitPlan(
        instance_name=instance_name,
        requested_port=requested_port,
        port=port,
        url=f"http://localhost:{port}",
        state=state,
        compose_path=compose_path,
        env_path=env_path,
        volume_name=volume_name,
        image_ref=image_ref,
        registered=registered,
        compose_exists=compose_exists,
        env_exists=env_exists,
        will_create_compose=not compose_exists,
        will_create_env=not env_exists,
        will_preserve_env=env_exists,
        will_register=will_register,
        will_start=True,
        will_open=will_open,
        requested_port_ignored=requested_port_ignored,
        steps=tuple(steps),
    )


def _load_registered_instance(instance_name: str) -> InstanceRecord | None:
    db_path = config_home() / "state.db"
    if not db_path.exists():
        return None

    with StateStore(db_path) as state:
        return state.get_instance(instance_name)


def _read_port_from_env(env_path: Path) -> int | None:
    raw_port = read_env_value(env_path, "N8N_PORT")
    if raw_port is None:
        return None

    try:
        return int(raw_port)
    except ValueError:
        return None


def _raise_if_prerequisites_fail(report: DoctorReport) -> None:
    for check in report.checks:
        if not check.ok:
            _raise_prerequisite_error(check)


def _raise_prerequisite_error(check: DoctorCheck) -> None:
    message = f"{check.name} is not ready: {check.detail}."
    if check.exit_code == 11:
        raise PortInUseError(message, hint=check.hint)
    if check.exit_code == 10:
        raise PrerequisiteError(message, hint=check.hint)
    raise LonError(message, hint=check.hint)


def _report(progress: ProgressReporter | None, message: str) -> None:
    if progress is not None:
        progress(message)
