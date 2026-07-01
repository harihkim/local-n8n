from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from local_n8n.core.doctor import run_doctor
from local_n8n.core.errors import LonError
from local_n8n.core.instance import (
    down_instance,
    logs_instance,
    open_instance,
    restart_instance,
    start_instance,
    status_instance,
    stop_instance,
    up_instance,
)

app = typer.Typer(
    add_completion=False,
    help="Manage a local, portable n8n instance.",
    no_args_is_help=True,
)
console = Console(stderr=True)


def _handle_error(error: LonError) -> None:
    console.print(f"[bold red]Error:[/bold red] {error.message}")
    if error.hint:
        console.print(f"[dim]{error.hint}[/dim]")
    raise typer.Exit(error.exit_code)


@app.command()
def up(
    instance: str = typer.Option("default", "--instance", "-i", help="Instance name."),
    port: int | None = typer.Option(None, "--port", "-p", help="Host port for n8n."),
) -> None:
    """Render the instance files if needed and start n8n."""
    console.print("[cyan]Starting n8n and waiting for the editor...[/cyan]")
    try:
        result = up_instance(instance_name=instance, port=port)
    except LonError as error:
        _handle_error(error)

    console.print(f"[green]n8n is running:[/green] {result.url}")
    console.print(f"[dim]compose: {result.compose_path}[/dim]")


@app.command()
def down(
    instance: str = typer.Option("default", "--instance", "-i", help="Instance name."),
) -> None:
    """Remove the n8n container while keeping the Docker volume."""
    console.print("[cyan]Removing n8n container and keeping the data volume...[/cyan]")
    try:
        result = down_instance(instance_name=instance)
    except LonError as error:
        _handle_error(error)

    console.print(f"[green]n8n container removed.[/green] Volume kept: {result.volume_name}")


@app.command()
def stop(
    instance: str = typer.Option("default", "--instance", "-i", help="Instance name."),
) -> None:
    """Stop n8n while keeping the container and Docker volume."""
    console.print("[cyan]Stopping n8n container and keeping it available for start...[/cyan]")
    try:
        result = stop_instance(instance_name=instance)
    except LonError as error:
        _handle_error(error)

    console.print(f"[green]n8n stopped.[/green] Container kept. Volume kept: {result.volume_name}")


@app.command()
def start(
    instance: str = typer.Option("default", "--instance", "-i", help="Instance name."),
) -> None:
    """Start an existing stopped n8n container."""
    console.print("[cyan]Checking n8n container and starting...[/cyan]")
    try:
        result = start_instance(instance_name=instance)
    except LonError as error:
        _handle_error(error)

    console.print(f"[green]n8n started:[/green] {result.url}")


@app.command()
def restart(
    instance: str = typer.Option("default", "--instance", "-i", help="Instance name."),
) -> None:
    """Restart n8n and wait for the editor."""
    console.print("[cyan]Checking n8n container and restarting...[/cyan]")
    try:
        result = restart_instance(instance_name=instance)
    except LonError as error:
        _handle_error(error)

    console.print(f"[green]n8n restarted:[/green] {result.url}")


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
    table.add_row("Health", result.health or "-")
    table.add_row("Volume", result.volume_name)
    table.add_row("Compose", str(result.compose_path))
    console.print(table)


@app.command()
def logs(
    instance: str = typer.Option("default", "--instance", "-i", help="Instance name."),
    follow: bool = typer.Option(False, "--follow", "-f", help="Follow log output."),
    tail: int = typer.Option(100, "--tail", help="Number of log lines to show."),
) -> None:
    """Show n8n container logs."""
    console.print("[cyan]Fetching n8n logs...[/cyan]")
    try:
        result = logs_instance(instance_name=instance, follow=follow, tail=tail)
    except LonError as error:
        _handle_error(error)

    console.print(result.output.rstrip())


@app.command()
def open(
    instance: str = typer.Option("default", "--instance", "-i", help="Instance name."),
) -> None:
    """Open the n8n editor URL in a browser if possible."""
    console.print("[cyan]Opening n8n editor...[/cyan]")
    try:
        result = open_instance(instance_name=instance)
    except LonError as error:
        _handle_error(error)

    if result.opened:
        console.print(f"[green]Opened n8n:[/green] {result.url}")
    else:
        console.print(f"[yellow]Could not open a browser. Use:[/yellow] {result.url}")


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

    if not report.ok:
        raise typer.Exit(report.exit_code)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
