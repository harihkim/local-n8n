from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP_SCRIPT = ROOT / "scripts" / "bootstrap-windows.ps1"
INSTALLER_SCRIPT = ROOT / "scripts" / "install-windows-launcher.ps1"
LAUNCHER_SCRIPT = ROOT / "scripts" / "lon.ps1"
WINDOWS_DOC = ROOT / "docs" / "windows.md"


def test_windows_bootstrap_script_keeps_user_choice_explicit() -> None:
    text = BOOTSTRAP_SCRIPT.read_text(encoding="utf-8")

    assert '[ValidateSet("Desktop", "Engine")]' in text
    assert '$DockerMode = "Desktop"' in text
    assert "wsl.exe" in text
    assert "WSL Integration" in text
    assert ".\\scripts\\install-windows-launcher.ps1" in text
    assert "lon doctor" in text
    assert "lon init" in text
    assert "Do not also enable Docker Desktop integration" in text
    assert "open Ubuntu and run" not in text


def test_windows_installer_creates_plain_lon_command() -> None:
    text = INSTALLER_SCRIPT.read_text(encoding="utf-8")

    assert '[ValidateSet("Repo", "Tool")]' in text
    assert '$Mode = "Repo"' in text
    assert "lon.cmd" in text
    assert "lon-wsl.ps1" in text
    assert "Add-UserPath" in text
    assert "lon init" in text


def test_windows_launcher_runs_lon_inside_wsl() -> None:
    text = LAUNCHER_SCRIPT.read_text(encoding="utf-8")

    assert "$UseRepo = $false" in text
    assert 'if ($arg -eq "-UseRepo")' in text
    assert "Convert-ToWslPath" in text
    assert '@("uv", "run", "lon")' in text
    assert '@("lon")' in text
    assert "& wsl.exe @wslArgs @command @LonArgs" in text


def test_windows_setup_docs_cover_both_docker_paths() -> None:
    text = WINDOWS_DOC.read_text(encoding="utf-8")

    assert "use PowerShell as the main interface" in text
    assert "Docker Desktop with WSL integration" in text
    assert "Docker Engine directly inside WSL" in text
    assert ".\\scripts\\bootstrap-windows.ps1" in text
    assert ".\\scripts\\install-windows-launcher.ps1" in text
    assert ".\\scripts\\lon.ps1 -UseRepo doctor" in text
    assert "lon init" in text
    assert "-DockerMode Engine" in text
    assert "Ubuntu shell" in text
