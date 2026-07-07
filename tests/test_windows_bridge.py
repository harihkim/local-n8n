from __future__ import annotations

import subprocess

import pytest

import local_n8n.windows_bridge as bridge


def test_windows_bridge_noops_on_non_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bridge.platform, "system", lambda: "Linux")

    assert bridge.maybe_delegate_to_wsl(["doctor"]) is None


def test_windows_bridge_delegates_plain_lon_to_wsl(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bridge.platform, "system", lambda: "Windows")
    monkeypatch.setattr(bridge, "_wsl_executable", lambda: "wsl.exe")
    monkeypatch.setattr(bridge, "_wsl_cwd", lambda distro: "/home/hari/project")
    captured: list[list[str]] = []

    def fake_run(
        args: list[str], check: bool = False, **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        captured.append(args)
        return subprocess.CompletedProcess(args=args, returncode=7)

    monkeypatch.setattr(bridge.subprocess, "run", fake_run)

    exit_code = bridge.maybe_delegate_to_wsl(["doctor", "--port", "5678"])

    assert exit_code == 7
    assert captured == [
        [
            "wsl.exe",
            "-d",
            "Ubuntu",
            "--cd",
            "/home/hari/project",
            "--exec",
            "sh",
            "-lc",
            bridge._wsl_package_command(),
            "local-n8n",
            "local-n8n",
            "doctor",
            "--port",
            "5678",
        ]
    ]


def test_windows_bridge_can_delegate_checkout_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(bridge.WINDOWS_REPO_ENV, r"C:\Users\hari\local-n8n")
    monkeypatch.setattr(bridge, "_wsl_executable", lambda: "wsl.exe")
    monkeypatch.setattr(bridge, "_wsl_cwd", lambda distro: None)

    def fake_run(
        args: list[str],
        check: bool = False,
        capture_output: bool = False,
        text: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        assert args[-1] == r"C:\Users\hari\local-n8n"
        return subprocess.CompletedProcess(
            args=args, returncode=0, stdout="/mnt/c/Users/hari/local-n8n\n"
        )

    monkeypatch.setattr(bridge.subprocess, "run", fake_run)

    command = bridge.build_wsl_command(["doctor"], distro="Ubuntu")

    assert command[:4] == ["wsl.exe", "-d", "Ubuntu", "--exec"]
    assert command[4:8] == [
        "sh",
        "-lc",
        'cd "$1" && shift && exec uv run lon "$@"',
        "local-n8n-repo",
    ]
    assert command[8:] == ["/mnt/c/Users/hari/local-n8n", "doctor"]


def test_windows_bridge_supports_package_spec_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        bridge.WINDOWS_PACKAGE_SPEC_ENV,
        "git+https://github.com/harihkim/local-n8n.git@v0.1.0a3",
    )
    monkeypatch.setattr(bridge, "_wsl_executable", lambda: "wsl.exe")
    monkeypatch.setattr(bridge, "_wsl_cwd", lambda distro: None)

    command = bridge.build_wsl_command(["doctor"], distro="Ubuntu")

    assert command[-2:] == [
        "git+https://github.com/harihkim/local-n8n.git@v0.1.0a3",
        "doctor",
    ]


def test_windows_bridge_converts_windows_path_arguments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(bridge, "_wsl_executable", lambda: "wsl.exe")

    def fake_run(
        args: list[str],
        check: bool = False,
        capture_output: bool = False,
        text: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        path = args[-1].replace("\\", "/")
        converted = "/mnt/" + path[0].lower() + path[2:]
        return subprocess.CompletedProcess(args=args, returncode=0, stdout=f"{converted}\n")

    monkeypatch.setattr(bridge.subprocess, "run", fake_run)

    assert bridge._to_wsl_arg(r"C:\Users\hari\backup.n8nbundle", distro="Ubuntu") == (
        "/mnt/c/Users/hari/backup.n8nbundle"
    )
    assert bridge._to_wsl_arg(r"--output=C:\Users\hari\backup.n8nbundle", distro="Ubuntu") == (
        "--output=/mnt/c/Users/hari/backup.n8nbundle"
    )


def test_windows_bridge_converts_wsl_unc_path() -> None:
    assert (
        bridge._to_wsl_arg(
            r"\\wsl.localhost\Ubuntu\home\hari\backup.n8nbundle",
            distro="Ubuntu",
        )
        == "/home/hari/backup.n8nbundle"
    )


def test_windows_bridge_reports_missing_wsl(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(bridge.platform, "system", lambda: "Windows")
    monkeypatch.setattr(bridge, "build_wsl_command", lambda args, distro: ["wsl.exe", "--version"])

    def fake_run(args: list[str], check: bool = False) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError("wsl.exe")

    monkeypatch.setattr(bridge.subprocess, "run", fake_run)

    assert bridge.maybe_delegate_to_wsl(["doctor"]) == 10
    assert "requires WSL" in capsys.readouterr().err


def test_windows_bridge_can_be_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bridge.platform, "system", lambda: "Windows")
    monkeypatch.setenv(bridge.WINDOWS_BRIDGE_ENV, "0")

    assert bridge.maybe_delegate_to_wsl(["doctor"]) is None
