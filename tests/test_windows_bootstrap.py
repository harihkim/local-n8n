from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "bootstrap-windows.ps1"
WINDOWS_DOC = ROOT / "docs" / "windows.md"


def test_windows_bootstrap_script_keeps_user_choice_explicit() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert '[ValidateSet("Desktop", "Engine")]' in text
    assert '$DockerMode = "Desktop"' in text
    assert "wsl.exe" in text
    assert "WSL Integration" in text
    assert "lon --dry-run doctor --fix" in text
    assert "Do not also enable Docker Desktop integration" in text


def test_windows_setup_docs_cover_both_docker_paths() -> None:
    text = WINDOWS_DOC.read_text(encoding="utf-8")

    assert "Docker Desktop with WSL integration" in text
    assert "Docker Engine directly inside WSL" in text
    assert ".\\scripts\\bootstrap-windows.ps1" in text
    assert "-DockerMode Engine" in text
