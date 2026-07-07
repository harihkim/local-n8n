from pathlib import Path

import pytest

from local_n8n.core.config import config_home
from local_n8n.core.doctor import DoctorCheck, run_doctor
from local_n8n.core.runner import CommandResult

ROOT = Path(__file__).resolve().parents[1]
WINDOWS_DOC = ROOT / "docs" / "windows.md"
WINDOWS_HELPER = ROOT / "scripts" / "check-windows-prereqs.ps1"


def test_windows_docs_are_native_powershell_first() -> None:
    text = WINDOWS_DOC.read_text(encoding="utf-8")

    assert "WSL is not required for normal Windows use" in text
    assert "uv tool install local-n8n" in text
    assert "pipx install local-n8n" in text
    assert "lon init" in text
    assert "%LOCALAPPDATA%\\local-n8n\\" in text
    assert "delegates into WSL" not in text


def test_windows_prereq_helper_does_not_install_wsl() -> None:
    text = WINDOWS_HELPER.read_text(encoding="utf-8")

    assert "Docker Desktop for Windows" in text
    assert "lon doctor" in text
    assert "lon init" in text
    assert "wsl.exe" not in text


def test_config_home_uses_localappdata_on_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LOCAL_N8N_HOME", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", r"C:\Users\hari\AppData\Local")
    monkeypatch.setattr("local_n8n.core.config.platform.system", lambda: "Windows")

    assert config_home() == Path(r"C:\Users\hari\AppData\Local") / "local-n8n"


def test_doctor_accepts_windows_docker_desktop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("local_n8n.core.doctor.platform.system", lambda: "Windows")
    monkeypatch.setattr("local_n8n.core.doctor._is_wsl", lambda: False)
    monkeypatch.setattr(
        "local_n8n.core.doctor.shutil.which",
        lambda name: r"C:\Program Files\Docker\docker.exe",
    )
    monkeypatch.setattr(
        "local_n8n.core.doctor._port_check",
        lambda port: DoctorCheck("Port 0", True, "available"),
    )

    def fake_run(args: list[str], cwd: Path) -> CommandResult:
        if args == ["docker", "info"]:
            return CommandResult(args=args, returncode=0, stdout="", stderr="")
        if args == ["docker", "info", "--format", "{{json .}}"]:
            return CommandResult(
                args=args,
                returncode=0,
                stdout='{"OperatingSystem":"Docker Desktop","Name":"docker-desktop"}',
                stderr="",
            )
        if args == ["docker", "context", "show"]:
            return CommandResult(args=args, returncode=0, stdout="desktop-linux\n", stderr="")
        if args == ["docker", "compose", "version"]:
            return CommandResult(
                args=args, returncode=0, stdout="Docker Compose version v5.1.4", stderr=""
            )
        raise AssertionError(args)

    monkeypatch.setattr("local_n8n.core.doctor.run", fake_run)

    report = run_doctor(port=0)

    backend = next(check for check in report.checks if check.name == "Docker backend")
    assert report.ok
    assert backend.detail == "Docker Desktop; name=docker-desktop; context=desktop-linux"
    assert backend.hint == "Docker Desktop for Windows is active."


def test_doctor_windows_missing_docker_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("local_n8n.core.doctor.platform.system", lambda: "Windows")
    monkeypatch.setattr("local_n8n.core.doctor.shutil.which", lambda name: None)
    monkeypatch.setattr(
        "local_n8n.core.doctor._port_check",
        lambda port: DoctorCheck("Port 0", True, "available"),
    )

    def fake_run(args: list[str], cwd: Path) -> CommandResult:
        raise FileNotFoundError("docker")

    monkeypatch.setattr("local_n8n.core.doctor.run", fake_run)

    report = run_doctor(port=0)

    cli = next(check for check in report.checks if check.name == "Docker CLI")
    assert not cli.ok
    assert cli.hint == "Install Docker Desktop for Windows, start it, then re-run doctor."


def test_windows_open_commands_use_windows_shell(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("local_n8n.core.instance._is_wsl", lambda: False)
    monkeypatch.setattr("local_n8n.core.instance.platform.system", lambda: "Windows")

    from local_n8n.core.instance import _open_commands

    assert _open_commands("http://localhost:5678") == [
        ["cmd", "/c", "start", "", "http://localhost:5678"],
        ["powershell", "-NoProfile", "Start-Process", "http://localhost:5678"],
    ]
