from __future__ import annotations

import json as json_lib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from local_n8n.core.config import build_instance_config
from local_n8n.core.diagnostics import debug, set_verbose
from local_n8n.core.doctor import run_doctor
from local_n8n.core.errors import LonError, UsageError
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


def _handle_error(error: LonError) -> None:
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

    writes = []
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
        result = up_instance(instance_name=instance, port=port, progress=_progress)
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
