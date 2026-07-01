from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from local_n8n.app import app
from local_n8n.core.runner import CommandResult

runner = CliRunner()


def test_cli_up_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))

    def fake_run(args: list[str], cwd: Path) -> CommandResult:
        return CommandResult(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr("local_n8n.core.instance.run", fake_run)

    result = runner.invoke(app, ["up"])

    assert result.exit_code == 0
    assert "n8n is running" in result.stderr


def test_cli_up_friendly_error_without_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))

    def fake_run(args: list[str], cwd: Path) -> CommandResult:
        raise FileNotFoundError("docker")

    monkeypatch.setattr("local_n8n.core.instance.run", fake_run)

    result = runner.invoke(app, ["up"])

    assert result.exit_code == 10
    assert "Docker was not found" in result.stderr
    assert "Traceback" not in result.stderr
