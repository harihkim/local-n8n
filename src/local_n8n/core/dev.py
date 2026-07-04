from __future__ import annotations

import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from local_n8n.compose.template import DEFAULT_IMAGE_REF
from local_n8n.core.config import build_instance_config, config_home, validate_instance_name
from local_n8n.core.errors import CommandFailedError, PrerequisiteError, UsageError
from local_n8n.core.runner import CommandResult, run, run_streaming
from local_n8n.core.state import StateStore

ProgressReporter = Callable[[str], None]


@dataclass(frozen=True)
class DevWipeTarget:
    name: str
    project_name: str
    compose_path: Path
    volume_name: str


@dataclass(frozen=True)
class DevWipePlan:
    config_home: Path
    targets: tuple[DevWipeTarget, ...]
    volume_names: tuple[str, ...]
    image_refs: tuple[str, ...]
    local_paths: tuple[Path, ...]


@dataclass(frozen=True)
class DevWipeResult:
    plan: DevWipePlan
    docker_commands: tuple[tuple[str, ...], ...]
    deleted_paths: tuple[Path, ...]


def plan_dev_wipe(include_images: bool = False) -> DevWipePlan:
    home = config_home()
    instance_names = _instance_names(home)
    targets = tuple(_target_for_name(name) for name in instance_names)
    volume_names = tuple(
        sorted({target.volume_name for target in targets} | _registered_volumes(home))
    )
    image_refs = tuple(sorted(_image_refs(home, targets))) if include_images else ()
    return DevWipePlan(
        config_home=home,
        targets=targets,
        volume_names=volume_names,
        image_refs=image_refs,
        local_paths=_local_paths(home),
    )


def wipe_dev(
    plan: DevWipePlan | None = None,
    progress: ProgressReporter | None = None,
) -> DevWipeResult:
    active_plan = plan or plan_dev_wipe()
    commands: list[tuple[str, ...]] = []

    for target in active_plan.targets:
        _report(progress, f"Removing Docker resources for {target.name!r}...")
        if target.compose_path.exists():
            commands.append(
                _run_streaming(
                    [
                        "docker",
                        "compose",
                        "-p",
                        target.project_name,
                        "-f",
                        str(target.compose_path),
                        "down",
                        "-v",
                        "--remove-orphans",
                    ]
                )
            )
        commands.extend(_remove_labeled_docker_objects(target.project_name))

    for volume_name in active_plan.volume_names:
        _report(progress, f"Removing Docker volume {volume_name!r}...")
        command = ["docker", "volume", "rm", "--force", volume_name]
        result = _run(command)
        commands.append(tuple(command))
        if result.returncode != 0 and not _is_missing_resource(result):
            _raise_command_failed(result)

    for image_ref in active_plan.image_refs:
        _report(progress, f"Removing Docker image {image_ref!r}...")
        command = ["docker", "image", "rm", "--force", image_ref]
        result = _run(command)
        commands.append(tuple(command))
        if result.returncode != 0 and not _is_missing_resource(result):
            _raise_command_failed(result)

    _report(progress, "Deleting local instance files and state...")
    deleted_paths = tuple(path for path in active_plan.local_paths if _delete_path(path))
    return DevWipeResult(
        plan=active_plan,
        docker_commands=tuple(commands),
        deleted_paths=deleted_paths,
    )


def _instance_names(home: Path) -> tuple[str, ...]:
    names = set(_registered_instance_names(home))
    instances_dir = home / "instances"
    if instances_dir.exists():
        for path in instances_dir.iterdir():
            if path.is_dir() and _is_valid_instance_name(path.name):
                names.add(path.name)
    return tuple(sorted(names))


def _registered_instance_names(home: Path) -> set[str]:
    state_path = home / "state.db"
    if not state_path.exists():
        return set()

    with StateStore(state_path) as state:
        return {record.name for record in state.list_instances()}


def _registered_volumes(home: Path) -> set[str]:
    state_path = home / "state.db"
    if not state_path.exists():
        return set()

    with StateStore(state_path) as state:
        return {record.data_volume for record in state.list_instances()}


def _registered_image_refs(home: Path) -> set[str]:
    state_path = home / "state.db"
    if not state_path.exists():
        return set()

    with StateStore(state_path) as state:
        return {record.image_ref for record in state.list_instances()}


def _image_refs(home: Path, targets: tuple[DevWipeTarget, ...]) -> set[str]:
    raw_refs = {DEFAULT_IMAGE_REF} | _registered_image_refs(home)
    for target in targets:
        raw_refs.add(build_instance_config(target.name).image_ref)

    refs: set[str] = set()
    for image_ref in raw_refs:
        refs.update(_image_ref_variants(image_ref))
    return refs


def _image_ref_variants(image_ref: str) -> set[str]:
    if "@" not in image_ref:
        return {image_ref}

    tagged_ref, digest = image_ref.split("@", 1)
    repository_ref = _strip_image_tag(tagged_ref)
    return {
        image_ref,
        tagged_ref,
        f"{repository_ref}@{digest}",
    }


def _strip_image_tag(image_ref: str) -> str:
    last_slash = image_ref.rfind("/")
    last_colon = image_ref.rfind(":")
    if last_colon > last_slash:
        return image_ref[:last_colon]
    return image_ref


def _target_for_name(name: str) -> DevWipeTarget:
    config = build_instance_config(name)
    return DevWipeTarget(
        name=name,
        project_name=config.project_name,
        compose_path=config.compose_path,
        volume_name=config.volume_name,
    )


def _local_paths(home: Path) -> tuple[Path, ...]:
    candidates = [
        home / "instances",
        home / "state.db",
        home / "state.db-wal",
        home / "state.db-shm",
        home / "state.db-journal",
    ]
    return tuple(path for path in candidates if path.exists())


def _remove_labeled_docker_objects(project_name: str) -> tuple[tuple[str, ...], ...]:
    commands: list[tuple[str, ...]] = []
    containers = _list_docker_objects(
        ["docker", "container", "ls", "--all", "--quiet", "--filter", _project_label(project_name)]
    )
    if containers:
        commands.append(_run_streaming(["docker", "container", "rm", "--force", *containers]))

    networks = _list_docker_objects(
        ["docker", "network", "ls", "--quiet", "--filter", _project_label(project_name)]
    )
    if networks:
        commands.append(_run_ignoring_missing(["docker", "network", "rm", *networks]))

    volumes = _list_docker_objects(
        ["docker", "volume", "ls", "--quiet", "--filter", _project_label(project_name)]
    )
    if volumes:
        commands.append(_run_ignoring_missing(["docker", "volume", "rm", "--force", *volumes]))

    return tuple(commands)


def _list_docker_objects(command: list[str]) -> list[str]:
    result = _run(command)
    _raise_if_failed(result)
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _project_label(project_name: str) -> str:
    return f"label=com.docker.compose.project={project_name}"


def _run(command: list[str]) -> CommandResult:
    try:
        return run(command, cwd=Path.cwd())
    except FileNotFoundError as exc:
        raise PrerequisiteError(
            "Docker was not found.",
            hint="Install Docker Engine inside WSL/Linux, then re-run this command.",
        ) from exc


def _run_streaming(command: list[str]) -> tuple[str, ...]:
    try:
        result = run_streaming(command, cwd=Path.cwd())
    except FileNotFoundError as exc:
        raise PrerequisiteError(
            "Docker was not found.",
            hint="Install Docker Engine inside WSL/Linux, then re-run this command.",
        ) from exc
    _raise_if_failed(result)
    return tuple(command)


def _run_ignoring_missing(command: list[str]) -> tuple[str, ...]:
    result = _run(command)
    if result.returncode != 0 and not _is_missing_resource(result):
        _raise_command_failed(result)
    return tuple(command)


def _raise_if_failed(result: CommandResult) -> None:
    if result.returncode != 0:
        _raise_command_failed(result)


def _raise_command_failed(result: CommandResult) -> None:
    raise CommandFailedError(
        "Docker cleanup command failed.",
        hint=result.stderr.strip() or result.stdout.strip() or "Run again with --verbose.",
    )


def _is_missing_resource(result: CommandResult) -> bool:
    output = f"{result.stderr}\n{result.stdout}".lower()
    return "no such" in output or "not found" in output


def _delete_path(path: Path) -> bool:
    if not path.exists():
        return False
    if path.is_dir():
        shutil.rmtree(path)
        return True
    path.unlink()
    return True


def _is_valid_instance_name(name: str) -> bool:
    try:
        validate_instance_name(name)
    except UsageError:
        return False
    return True


def _report(progress: ProgressReporter | None, message: str) -> None:
    if progress is not None:
        progress(message)
