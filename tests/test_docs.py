from __future__ import annotations

import re
import shlex
from pathlib import Path

from typer.testing import CliRunner

from local_n8n.app import app

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
COMMANDS_DOC = DOCS / "commands.md"

runner = CliRunner()

COMMAND_OPTIONS = {
    "up": {"--instance", "-i", "--port", "-p"},
    "down": {"--instance", "-i"},
    "stop": {"--instance", "-i"},
    "start": {"--instance", "-i"},
    "restart": {"--instance", "-i"},
    "status": {"--instance", "-i"},
    "logs": {"--instance", "-i", "--follow", "-f", "--tail"},
    "open": {"--instance", "-i"},
    "doctor": {"--port", "-p"},
}

GLOBAL_OPTIONS = {"--verbose", "--json", "--dry-run", "--yes", "-y"}


def test_commands_page_documents_registered_commands() -> None:
    text = COMMANDS_DOC.read_text(encoding="utf-8")

    for command in _registered_command_names():
        assert f"### `lon {command}`" in text


def test_commands_page_documents_global_options() -> None:
    text = COMMANDS_DOC.read_text(encoding="utf-8")

    for option in GLOBAL_OPTIONS:
        assert f"`{option}`" in text


def test_commands_page_documents_command_options() -> None:
    text = COMMANDS_DOC.read_text(encoding="utf-8")

    for command, options in COMMAND_OPTIONS.items():
        assert command in _registered_command_names()
        for option in options:
            assert f"`{option}`" in text


def test_safe_bash_examples_run() -> None:
    examples = _safe_bash_examples()
    assert examples

    for example in examples:
        args = _lon_args(example)
        result = runner.invoke(app, args)
        assert result.exit_code == 0, example


def _registered_command_names() -> set[str]:
    names = set()
    for command in app.registered_commands:
        if command.name is not None:
            name = command.name
        else:
            assert command.callback is not None
            callback_name = getattr(command.callback, "__name__", None)
            assert callback_name is not None
            name = callback_name.replace("_command", "")
        names.add(name.replace("_", "-"))
    return names


def _safe_bash_examples() -> list[str]:
    examples: list[str] = []
    for path in DOCS.glob("*.md"):
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r"```bash test\n(.*?)\n```", text, flags=re.DOTALL):
            block = match.group(1)
            for raw_line in block.splitlines():
                line = raw_line.strip()
                if line and not line.startswith("#"):
                    examples.append(line.removeprefix("$ ").strip())
    return examples


def _lon_args(example: str) -> list[str]:
    parts = shlex.split(example)
    if parts[:3] == ["uv", "run", "lon"]:
        return parts[3:]
    if parts[:1] == ["lon"]:
        return parts[1:]
    raise AssertionError(f"Unsupported docs test command: {example}")
