from __future__ import annotations

import getpass
import json as json_lib
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, NoReturn

import typer
from rich.console import Console
from rich.table import Table

from local_n8n.core.backup import backup_instance, restore_instance
from local_n8n.core.config import build_instance_config
from local_n8n.core.dev import DevWipePlan, DevWipeResult, plan_dev_wipe, wipe_dev
from local_n8n.core.diagnostics import debug, set_verbose
from local_n8n.core.doctor import run_doctor
from local_n8n.core.errors import LonError, UsageError
from local_n8n.core.init import InitPlan, InitResult, init_instance, plan_init
from local_n8n.core.instance import (
    down_instance,
    list_instances,
    logs_instance,
    open_instance,
    restart_instance,
    start_instance,
    status_instance,
    stop_instance,
    up_instance,
)


@dataclass
class CliOptions:
    json_output: bool = False
    dry_run: bool = False
    assume_yes: bool = False


app = typer.Typer(
    add_completion=False,
    help="Manage a local, portable n8n instance.",
    no_args_is_help=True,
)
dev_app = typer.Typer(
    add_completion=False,
    help="Development-only destructive commands.",
    no_args_is_help=True,
)
app.add_typer(dev_app, name="dev")
console = Console(stderr=True)
options = CliOptions()


@app.callback()
def app_options(
    verbose: bool = typer.Option(False, "--verbose", help="Show diagnostic output."),
    json_output: bool = typer.Option(False, "--json", help="Emit one JSON object to stdout."),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show the planned action without changes."
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Assume yes for confirmation prompts."),
) -> None:
    """Manage a local, portable n8n instance."""
    options.json_output = json_output
    options.dry_run = dry_run
    options.assume_yes = yes
    set_verbose(verbose)
    debug("verbose diagnostics enabled")


def _emit_json(payload: dict[str, Any]) -> None:
    typer.echo(json_lib.dumps(payload, sort_keys=True), color=False)


def _maybe_emit_json(payload: dict[str, Any]) -> None:
    if options.json_output:
        _emit_json(payload)


def _handle_error(error: LonError) -> NoReturn:
    console.print(f"[bold red]Error:[/bold red] {error.message}")
    if error.hint:
        console.print(f"[dim]{error.hint}[/dim]")
    _maybe_emit_json(
        {
            "ok": False,
            "error": {
                "message": error.message,
                "hint": error.hint,
                "exit_code": error.exit_code,
            },
        }
    )
    raise typer.Exit(error.exit_code)


def _progress(message: str) -> None:
    console.print(f"[cyan]{message}[/cyan]")


def _path(value: Path) -> str:
    return str(value)


def _dry_run_payload(
    *,
    command: str,
    instance: str,
    port: int | None = None,
    docker_action: str | None = None,
    writes_instance_files: bool = False,
    records_state: bool = False,
    waits_for_web_ui: bool = False,
) -> dict[str, Any]:
    config = build_instance_config(instance, port or 5678)
    docker_commands: list[list[str]] = []
    if docker_action is not None:
        docker_commands.append(
            [
                "docker",
                "compose",
                "-p",
                config.project_name,
                "-f",
                str(config.compose_path),
                docker_action,
            ]
        )
        if docker_action == "up":
            docker_commands[0].append("-d")

    writes: list[str] = []
    if writes_instance_files:
        writes = [_path(config.compose_path), _path(config.env_path)]
    if records_state:
        writes.append(_path(config.instance_dir.parent.parent / "state.db"))

    return {
        "ok": True,
        "command": command,
        "dry_run": True,
        "instance": instance,
        "url": f"http://localhost:{config.port}",
        "compose": _path(config.compose_path),
        "volume": config.volume_name,
        "would": {
            "write_files": writes,
            "docker_commands": docker_commands,
            "wait_for_web_ui": waits_for_web_ui,
        },
    }


def _backup_dry_run_payload(
    *,
    instance: str,
    output: Path | None,
) -> dict[str, Any]:
    config = build_instance_config(instance)
    bundle_path = output or (
        config.instance_dir.parent.parent / "backups" / f"{instance}-<timestamp>.n8nbundle"
    )
    return {
        "ok": True,
        "command": "backup",
        "dry_run": True,
        "instance": instance,
        "would": {
            "confirm_downtime": True,
            "prompt_passphrase": True,
            "stop_if_running": True,
            "capture_volume": config.volume_name,
            "write_bundle": _path(bundle_path),
            "write_recovery_material_if_missing": _path(config.instance_dir / "recovery.wrapped"),
            "record_state": _path(config.instance_dir.parent.parent / "state.db"),
            "restart_if_was_running": True,
        },
    }


def _restore_dry_run_payload(
    *,
    bundle: Path,
    replace: bool,
    port: int | None,
) -> dict[str, Any]:
    return {
        "ok": True,
        "command": "restore",
        "dry_run": True,
        "bundle": _path(bundle),
        "would": {
            "prompt_secret": True,
            "decrypt_bundle": True,
            "verify_manifest": True,
            "refuse_existing_without_replace": not replace,
            "create_pre_restore_backup_when_replacing": replace,
            "restore_volume": True,
            "write_instance_files": True,
            "register_state": True,
            "start": True,
            "wait_for_web_ui": True,
            "port_override": port,
        },
    }


def _emit_dry_run(payload: dict[str, Any]) -> None:
    if options.json_output:
        _emit_json(payload)
        return

    console.print("[yellow]Dry run. No changes made.[/yellow]")
    console.print(f"[dim]command: {payload['command']}[/dim]")
    console.print(f"[dim]instance: {payload['instance']}[/dim]")
    console.print(f"[dim]url: {payload['url']}[/dim]")
    for command in payload["would"]["docker_commands"]:
        console.print(f"[dim]would run: {' '.join(command)}[/dim]")
    for path in payload["would"]["write_files"]:
        console.print(f"[dim]would write: {path}[/dim]")
    if payload["would"]["wait_for_web_ui"]:
        console.print("[dim]would wait for n8n web UI readiness[/dim]")


def _emit_backup_dry_run(payload: dict[str, Any]) -> None:
    if options.json_output:
        _emit_json(payload)
        return

    console.print("[yellow]Dry run. No changes made.[/yellow]")
    console.print("[dim]command: backup[/dim]")
    console.print(f"[dim]instance: {payload['instance']}[/dim]")
    console.print("[dim]would ask before stopping n8n[/dim]")
    console.print("[dim]would prompt for backup passphrase[/dim]")
    console.print(f"[dim]would capture volume: {payload['would']['capture_volume']}[/dim]")
    console.print(f"[dim]would write bundle: {payload['would']['write_bundle']}[/dim]")
    console.print(
        "[dim]would create recovery material if missing: "
        f"{payload['would']['write_recovery_material_if_missing']}[/dim]"
    )
    console.print("[dim]would restart n8n if it was running before backup[/dim]")


def _emit_restore_dry_run(payload: dict[str, Any]) -> None:
    if options.json_output:
        _emit_json(payload)
        return

    console.print("[yellow]Dry run. No changes made.[/yellow]")
    console.print("[dim]command: restore[/dim]")
    console.print(f"[dim]bundle: {payload['bundle']}[/dim]")
    console.print("[dim]would prompt for passphrase or recovery code[/dim]")
    console.print("[dim]would decrypt bundle and verify manifest[/dim]")
    if payload["would"]["create_pre_restore_backup_when_replacing"]:
        console.print("[dim]would create a pre-restore safety backup before replacing[/dim]")
    else:
        console.print("[dim]would refuse to overwrite an existing instance[/dim]")
    if payload["would"]["port_override"] is not None:
        console.print(
            f"[dim]would override restored port: {payload['would']['port_override']}[/dim]"
        )
    console.print("[dim]would restore Docker volume, write instance files, and start n8n[/dim]")


def _init_payload(
    plan: InitPlan,
    *,
    dry_run: bool,
    result: InitResult | None = None,
) -> dict[str, Any]:
    return {
        "ok": True,
        "command": "init",
        "dry_run": dry_run,
        "instance": plan.instance_name,
        "state": plan.state.value,
        "requested_port": plan.requested_port,
        "port": plan.port,
        "url": plan.url,
        "compose": _path(plan.compose_path),
        "env": _path(plan.env_path),
        "volume": plan.volume_name,
        "image": plan.image_ref,
        "requested_port_ignored": plan.requested_port_ignored,
        "steps": [step.value for step in plan.steps],
        "started": result.started if result is not None else False,
        "opened": result.opened if result is not None else False,
        "opener": result.opener if result is not None else None,
        "would": {
            "check_prerequisites": True,
            "create_compose": plan.will_create_compose,
            "create_env": plan.will_create_env,
            "preserve_env": plan.will_preserve_env,
            "register": plan.will_register,
            "start": plan.will_start,
            "open_browser": plan.will_open,
            "explain_owner_setup": True,
        },
    }


def _emit_init_dry_run(plan: InitPlan) -> None:
    payload = _init_payload(plan, dry_run=True)
    if options.json_output:
        _emit_json(payload)
        return

    console.print("[yellow]Dry run. No changes made.[/yellow]")
    console.print("[dim]command: init[/dim]")
    console.print(f"[dim]instance: {plan.instance_name} ({plan.state.value})[/dim]")
    console.print(f"[dim]url: {plan.url}[/dim]")
    console.print("[dim]would check: Docker prerequisites[/dim]")
    if plan.will_create_compose:
        console.print(f"[dim]would write: {plan.compose_path}[/dim]")
    if plan.will_create_env:
        console.print(f"[dim]would write: {plan.env_path}[/dim]")
    if plan.will_preserve_env:
        console.print(f"[dim]would preserve: {plan.env_path}[/dim]")
    if plan.will_register:
        console.print(f"[dim]would register: {plan.instance_name}[/dim]")
    console.print("[dim]would start n8n and wait for web UI readiness[/dim]")
    if plan.will_open:
        console.print("[dim]would open the n8n web UI[/dim]")
    console.print("[dim]would explain the local owner setup step[/dim]")


def _emit_owner_setup_guidance(plan: InitPlan, result: InitResult) -> None:
    console.print(f"[green]local-n8n is ready:[/green] {plan.url}")
    if plan.will_open:
        if result.opened:
            console.print(f"[green]Opened n8n in your browser.[/green] opener: {result.opener}")
        else:
            console.print(f"[yellow]Could not open a browser. Use:[/yellow] {plan.url}")
    else:
        console.print(f"[yellow]Open n8n:[/yellow] {plan.url}")
    console.print(
        "[dim]If n8n redirects to /setup, create the local owner account there. "
        "That account stays inside this local instance.[/dim]"
    )


def _dev_wipe_payload(
    plan: DevWipePlan,
    *,
    dry_run: bool,
    result: DevWipeResult | None = None,
) -> dict[str, Any]:
    return {
        "ok": True,
        "command": "dev wipe",
        "dry_run": dry_run,
        "config_home": _path(plan.config_home),
        "instances": [
            {
                "name": target.name,
                "project": target.project_name,
                "compose": _path(target.compose_path),
                "volume": target.volume_name,
            }
            for target in plan.targets
        ],
        "volumes": list(plan.volume_names),
        "images": list(plan.image_refs),
        "local_paths": [_path(path) for path in plan.local_paths],
        "docker_commands": [list(command) for command in result.docker_commands]
        if result is not None
        else [],
        "deleted_paths": [_path(path) for path in result.deleted_paths]
        if result is not None
        else [],
    }


def _emit_dev_wipe_dry_run(plan: DevWipePlan) -> None:
    payload = _dev_wipe_payload(plan, dry_run=True)
    if options.json_output:
        _emit_json(payload)
        return

    console.print("[yellow]Dry run. No changes made.[/yellow]")
    console.print("[bold red]Development wipe preview[/bold red]")
    console.print(f"[dim]config home: {plan.config_home}[/dim]")
    if not plan.targets and not plan.volume_names and not plan.image_refs and not plan.local_paths:
        console.print("[dim]Nothing local-n8n related found.[/dim]")
        return
    for target in plan.targets:
        console.print(f"[dim]would remove project: {target.project_name}[/dim]")
        console.print(f"[dim]would remove compose: {target.compose_path}[/dim]")
    for volume_name in plan.volume_names:
        console.print(f"[dim]would remove volume: {volume_name}[/dim]")
    for image_ref in plan.image_refs:
        console.print(f"[dim]would remove image: {image_ref}[/dim]")
    for path in plan.local_paths:
        console.print(f"[dim]would delete: {path}[/dim]")


def _confirm_dev_wipe(plan: DevWipePlan) -> bool:
    console.print("[bold red]Development wipe warning[/bold red]")
    console.print(
        "[red]This will delete local-n8n containers, networks, volumes, files, and state.[/red]"
    )
    if plan.image_refs:
        console.print("[red]It will also delete known local-n8n Docker images.[/red]")
    console.print(f"[dim]config home: {plan.config_home}[/dim]")
    try:
        answer = console.input("[bold red]Type yes to continue (default: no): [/bold red]")
    except EOFError:
        return False
    return answer.strip().lower() == "yes"


def _confirm_image_update(old_image_ref: str, new_image_ref: str) -> bool:
    if options.assume_yes:
        return True
    console.print("[yellow]n8n image update available.[/yellow]")
    console.print(f"[dim]current: {old_image_ref}[/dim]")
    console.print(f"[dim]new:     {new_image_ref}[/dim]")
    console.print(
        "[yellow]Updating n8n can run database migrations. "
        "Backup support is not implemented yet.[/yellow]"
    )
    try:
        answer = console.input("[bold yellow]Update n8n image now? (Y/n): [/bold yellow]")
    except EOFError:
        return False
    return answer.strip().lower() not in {"n", "no"}


def _confirm_backup() -> bool:
    if options.assume_yes:
        return True
    console.print("[yellow]Backup will briefly stop n8n for a consistent snapshot.[/yellow]")
    try:
        answer = console.input("[bold yellow]Continue with backup? (y/N): [/bold yellow]")
    except EOFError:
        return False
    return answer.strip().lower() in {"y", "yes"}


def _prompt_backup_passphrase() -> str:
    first = getpass.getpass("Backup passphrase: ", stream=sys.stderr)
    second = getpass.getpass("Confirm backup passphrase: ", stream=sys.stderr)
    if not first:
        raise UsageError("Backup passphrase cannot be empty.")
    if first != second:
        raise UsageError("Backup passphrases did not match.")
    return first


def _prompt_restore_secret() -> str:
    secret = getpass.getpass("Backup passphrase or recovery code: ", stream=sys.stderr)
    if not secret:
        raise UsageError("Backup passphrase or recovery code cannot be empty.")
    return secret


@dev_app.command("wipe")
def dev_wipe(
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip typed confirmation."),
    images: bool = typer.Option(
        False,
        "--images",
        help="Also remove known local-n8n Docker images.",
    ),
) -> None:
    """Remove all local-n8n dev containers, volumes, instance files, and state."""
    try:
        plan = plan_dev_wipe(include_images=images)
    except LonError as error:
        _handle_error(error)

    if options.dry_run:
        _emit_dev_wipe_dry_run(plan)
        return

    if not yes and not options.assume_yes and not _confirm_dev_wipe(plan):
        _handle_error(LonError("Development wipe cancelled.", hint="Nothing was deleted."))

    console.print("[bold red]Development wipe confirmed.[/bold red]")
    try:
        result = wipe_dev(plan, progress=_progress)
    except LonError as error:
        _handle_error(error)

    console.print("[green]local-n8n development data wiped.[/green]")
    console.print(f"[dim]instances: {len(result.plan.targets)}[/dim]")
    console.print(f"[dim]volumes: {len(result.plan.volume_names)}[/dim]")
    console.print(f"[dim]images: {len(result.plan.image_refs)}[/dim]")
    console.print(f"[dim]deleted local paths: {len(result.deleted_paths)}[/dim]")
    _maybe_emit_json(_dev_wipe_payload(result.plan, dry_run=False, result=result))


@app.command()
def init(
    instance: str = typer.Option("default", "--instance", "-i", help="Instance name."),
    port: int | None = typer.Option(None, "--port", "-p", help="Host port for n8n."),
    open_browser: bool = typer.Option(True, "--open/--no-open", help="Open n8n after init."),
) -> None:
    """Initialize, start, and optionally open a local n8n instance."""
    if options.dry_run:
        try:
            plan = plan_init(instance_name=instance, port=port, open_browser=open_browser)
        except LonError as error:
            _handle_error(error)
        _emit_init_dry_run(plan)
        return

    try:
        result = init_instance(
            instance_name=instance,
            port=port,
            open_browser=open_browser,
            progress=_progress,
            image_update_confirm=_confirm_image_update,
        )
    except LonError as error:
        _handle_error(error)

    _emit_owner_setup_guidance(result.plan, result)
    _maybe_emit_json(_init_payload(result.plan, dry_run=False, result=result))


@app.command()
def up(
    instance: str = typer.Option("default", "--instance", "-i", help="Instance name."),
    port: int | None = typer.Option(None, "--port", "-p", help="Host port for n8n."),
) -> None:
    """Render the instance files if needed and start n8n."""
    if options.dry_run:
        try:
            payload = _dry_run_payload(
                command="up",
                instance=instance,
                port=port,
                docker_action="up",
                writes_instance_files=True,
                records_state=True,
                waits_for_web_ui=True,
            )
        except LonError as error:
            _handle_error(error)
        _emit_dry_run(payload)
        return

    try:
        result = up_instance(
            instance_name=instance,
            port=port,
            progress=_progress,
            image_update_confirm=_confirm_image_update,
        )
    except LonError as error:
        _handle_error(error)

    console.print(f"[green]n8n is running:[/green] {result.url}")
    console.print(f"[dim]compose: {result.compose_path}[/dim]")
    _maybe_emit_json(
        {
            "ok": True,
            "command": "up",
            "instance": instance,
            "url": result.url,
            "compose": _path(result.compose_path),
            "volume": result.volume_name,
        }
    )


@app.command()
def down(
    instance: str = typer.Option("default", "--instance", "-i", help="Instance name."),
) -> None:
    """Remove the n8n container while keeping the Docker volume."""
    if options.dry_run:
        try:
            payload = _dry_run_payload(command="down", instance=instance, docker_action="down")
        except LonError as error:
            _handle_error(error)
        _emit_dry_run(payload)
        return

    try:
        result = down_instance(instance_name=instance, progress=_progress)
    except LonError as error:
        _handle_error(error)

    console.print(f"[green]n8n container removed.[/green] Volume kept: {result.volume_name}")
    _maybe_emit_json(
        {
            "ok": True,
            "command": "down",
            "instance": instance,
            "volume": result.volume_name,
        }
    )


@app.command()
def stop(
    instance: str = typer.Option("default", "--instance", "-i", help="Instance name."),
) -> None:
    """Stop n8n while keeping the container and Docker volume."""
    if options.dry_run:
        try:
            payload = _dry_run_payload(command="stop", instance=instance, docker_action="stop")
        except LonError as error:
            _handle_error(error)
        _emit_dry_run(payload)
        return

    try:
        result = stop_instance(instance_name=instance, progress=_progress)
    except LonError as error:
        _handle_error(error)

    console.print(f"[green]n8n stopped.[/green] Container kept. Volume kept: {result.volume_name}")
    _maybe_emit_json(
        {
            "ok": True,
            "command": "stop",
            "instance": instance,
            "volume": result.volume_name,
        }
    )


@app.command()
def start(
    instance: str = typer.Option("default", "--instance", "-i", help="Instance name."),
) -> None:
    """Start an existing stopped n8n container."""
    if options.dry_run:
        try:
            payload = _dry_run_payload(
                command="start",
                instance=instance,
                docker_action="start",
                waits_for_web_ui=True,
            )
        except LonError as error:
            _handle_error(error)
        _emit_dry_run(payload)
        return

    try:
        result = start_instance(instance_name=instance, progress=_progress)
    except LonError as error:
        _handle_error(error)

    console.print(f"[green]n8n started:[/green] {result.url}")
    _maybe_emit_json({"ok": True, "command": "start", "instance": instance, "url": result.url})


@app.command()
def restart(
    instance: str = typer.Option("default", "--instance", "-i", help="Instance name."),
) -> None:
    """Restart n8n and wait for the web UI."""
    if options.dry_run:
        try:
            payload = _dry_run_payload(
                command="restart",
                instance=instance,
                docker_action="restart",
                waits_for_web_ui=True,
            )
        except LonError as error:
            _handle_error(error)
        _emit_dry_run(payload)
        return

    try:
        result = restart_instance(instance_name=instance, progress=_progress)
    except LonError as error:
        _handle_error(error)

    console.print(f"[green]n8n restarted:[/green] {result.url}")
    _maybe_emit_json({"ok": True, "command": "restart", "instance": instance, "url": result.url})


@app.command()
def backup(
    instance: Annotated[str, typer.Option("--instance", "-i", help="Instance name.")] = "default",
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Backup bundle path."),
    ] = None,
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Skip downtime confirmation."),
    ] = False,
) -> None:
    """Create an encrypted local backup bundle."""
    if options.dry_run:
        try:
            payload = _backup_dry_run_payload(instance=instance, output=output)
        except LonError as error:
            _handle_error(error)
        _emit_backup_dry_run(payload)
        return

    if not yes and not _confirm_backup():
        _handle_error(LonError("Backup cancelled.", hint="Nothing was changed."))

    try:
        passphrase = _prompt_backup_passphrase()
        result = backup_instance(
            instance_name=instance,
            passphrase=passphrase,
            output_path=output,
            progress=_progress,
        )
    except LonError as error:
        _handle_error(error)

    console.print(f"[green]Encrypted backup created:[/green] {result.bundle_path}")
    console.print(f"[dim]sha256: {result.checksum}[/dim]")
    console.print(f"[dim]size: {result.size} bytes[/dim]")
    if result.recovery_code is not None:
        console.print("[bold yellow]Recovery code created. Store it somewhere safe.[/bold yellow]")
        console.print(f"[bold yellow]{result.recovery_code}[/bold yellow]")
        console.print(
            "[dim]Keep at least one of: a working instance, or an openable backup bundle.[/dim]"
        )
    _maybe_emit_json(
        {
            "ok": True,
            "command": "backup",
            "instance": result.instance,
            "bundle": _path(result.bundle_path),
            "checksum": result.checksum,
            "size": result.size,
            "recovery_code_created": result.recovery_code is not None,
            "restarted": result.restarted,
        }
    )


@app.command()
def restore(
    bundle: Annotated[Path, typer.Argument(help="Backup bundle to restore.")],
    replace: Annotated[
        bool,
        typer.Option("--replace", help="Replace an existing instance after a safety backup."),
    ] = False,
    port: Annotated[
        int | None,
        typer.Option("--port", "-p", help="Override the restored n8n port."),
    ] = None,
) -> None:
    """Restore an encrypted local backup bundle."""
    if options.dry_run:
        _emit_restore_dry_run(_restore_dry_run_payload(bundle=bundle, replace=replace, port=port))
        return

    try:
        secret = _prompt_restore_secret()
        result = restore_instance(
            bundle,
            secret=secret,
            replace=replace,
            port=port,
            progress=_progress,
        )
    except LonError as error:
        _handle_error(error)

    console.print(f"[green]Restored n8n:[/green] {result.url}")
    console.print(f"[dim]instance: {result.instance}[/dim]")
    console.print(f"[dim]volume: {result.volume_name}[/dim]")
    console.print(f"[dim]compose: {result.compose_path}[/dim]")
    if result.pre_restore_backup is not None:
        console.print(f"[dim]pre-restore backup: {result.pre_restore_backup}[/dim]")
    _maybe_emit_json(
        {
            "ok": True,
            "command": "restore",
            "instance": result.instance,
            "url": result.url,
            "compose": _path(result.compose_path),
            "env": _path(result.env_path),
            "volume": result.volume_name,
            "replaced": result.replaced,
            "pre_restore_backup": _path(result.pre_restore_backup)
            if result.pre_restore_backup is not None
            else None,
        }
    )


@app.command()
def status(
    instance: str = typer.Option("default", "--instance", "-i", help="Instance name."),
) -> None:
    """Show the registered instance and Docker container status."""
    console.print("[cyan]Checking n8n status...[/cyan]")
    try:
        result = status_instance(instance_name=instance)
    except LonError as error:
        _handle_error(error)

    table = Table(title=f"local-n8n: {result.name}")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("URL", result.url)
    table.add_row("Container", result.container_state)
    table.add_row("Web UI", result.web_ui_state)
    table.add_row("Volume", result.volume_name)
    table.add_row("Compose", str(result.compose_path))
    console.print(table)
    _maybe_emit_json(
        {
            "ok": True,
            "command": "status",
            "instance": result.name,
            "url": result.url,
            "container": result.container_state,
            "web_ui": result.web_ui_state,
            "volume": result.volume_name,
            "compose": _path(result.compose_path),
        }
    )


@app.command("list")
def list_command() -> None:
    """List registered local-n8n instances."""
    console.print("[cyan]Listing local-n8n instances...[/cyan]")
    try:
        results = list_instances()
    except LonError as error:
        _handle_error(error)

    if not results:
        console.print("[yellow]No local-n8n instances yet. Run `lon up` to create one.[/yellow]")
        _maybe_emit_json({"ok": True, "command": "list", "instances": []})
        return

    table = Table(title="local-n8n instances")
    table.add_column("Name")
    table.add_column("URL")
    table.add_column("Container")
    table.add_column("Volume")
    for result in results:
        table.add_row(result.name, result.url, result.container_state, result.volume_name)
    console.print(table)
    console.print("[dim]Use `lon status --instance <name>` for details.[/dim]")
    _maybe_emit_json(
        {
            "ok": True,
            "command": "list",
            "instances": [
                {
                    "name": result.name,
                    "url": result.url,
                    "container": result.container_state,
                    "volume": result.volume_name,
                }
                for result in results
            ],
        }
    )


@app.command()
def logs(
    instance: str = typer.Option("default", "--instance", "-i", help="Instance name."),
    follow: bool = typer.Option(False, "--follow", "-f", help="Follow log output."),
    tail: int = typer.Option(100, "--tail", help="Number of log lines to show."),
) -> None:
    """Show n8n container logs."""
    if options.json_output and follow:
        _handle_error(
            UsageError(
                "`lon --json logs --follow` is not supported yet.",
                hint="Run `lon logs --follow` for streaming text logs.",
            )
        )

    console.print("[cyan]Fetching n8n logs...[/cyan]")
    try:
        result = logs_instance(instance_name=instance, follow=follow, tail=tail)
    except LonError as error:
        _handle_error(error)

    console.print(result.output.rstrip())
    _maybe_emit_json(
        {
            "ok": True,
            "command": "logs",
            "instance": instance,
            "tail": tail,
            "output": result.output,
        }
    )


@app.command()
def open(
    instance: str = typer.Option("default", "--instance", "-i", help="Instance name."),
) -> None:
    """Open the n8n web UI URL in a browser if possible."""
    if options.dry_run:
        try:
            payload = _dry_run_payload(command="open", instance=instance)
        except LonError as error:
            _handle_error(error)
        payload["would"]["open_browser"] = True
        _emit_dry_run(payload)
        return

    console.print("[cyan]Opening n8n web UI...[/cyan]")
    try:
        result = open_instance(instance_name=instance)
    except LonError as error:
        _handle_error(error)

    if result.opened:
        console.print(f"[green]Opened n8n:[/green] {result.url}")
    else:
        console.print(f"[yellow]Could not open a browser. Use:[/yellow] {result.url}")
    _maybe_emit_json(
        {
            "ok": True,
            "command": "open",
            "instance": instance,
            "url": result.url,
            "opened": result.opened,
            "opener": result.opener,
        }
    )


@app.command()
def doctor(
    port: int = typer.Option(5678, "--port", "-p", help="Port to check."),
) -> None:
    """Run read-only diagnostics for local n8n prerequisites."""
    console.print("[cyan]Checking local-n8n prerequisites...[/cyan]")
    report = run_doctor(port=port)

    table = Table(title="local-n8n doctor")
    table.add_column("Check")
    table.add_column("Status")
    table.add_column("Detail")
    table.add_column("Hint")
    for check in report.checks:
        table.add_row(
            check.name,
            "[green]ok[/green]" if check.ok else "[red]fail[/red]",
            check.detail,
            check.hint or "",
        )
    console.print(table)
    _maybe_emit_json(
        {
            "ok": report.ok,
            "command": "doctor",
            "exit_code": report.exit_code,
            "checks": [
                {
                    "name": check.name,
                    "ok": check.ok,
                    "detail": check.detail,
                    "hint": check.hint,
                    "exit_code": check.exit_code,
                }
                for check in report.checks
            ],
        }
    )

    if not report.ok:
        raise typer.Exit(report.exit_code)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
