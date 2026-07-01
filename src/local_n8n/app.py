from __future__ import annotations

import typer
from rich.console import Console

from local_n8n.core.errors import LonError
from local_n8n.core.instance import down_instance, up_instance

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
    port: int = typer.Option(5678, "--port", "-p", help="Host port for n8n."),
) -> None:
    """Render the instance files if needed and start n8n."""
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
    """Stop n8n while keeping the Docker volume."""
    try:
        result = down_instance(instance_name=instance)
    except LonError as error:
        _handle_error(error)

    console.print(f"[green]n8n stopped.[/green] Volume kept: {result.volume_name}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
