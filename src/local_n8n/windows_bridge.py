from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

WINDOWS_BRIDGE_ENV = "LOCAL_N8N_WINDOWS_BRIDGE"
WINDOWS_DISTRO_ENV = "LOCAL_N8N_WINDOWS_DISTRO"
WINDOWS_PACKAGE_SPEC_ENV = "LOCAL_N8N_WINDOWS_PACKAGE_SPEC"
WINDOWS_REPO_ENV = "LOCAL_N8N_WINDOWS_REPO"
WINDOWS_INNER_ENV = "LOCAL_N8N_WINDOWS_BRIDGE_INNER"

DEFAULT_DISTRO = "Ubuntu"
DISABLED_VALUES = {"0", "false", "no", "off"}
WINDOWS_ABSOLUTE_PATH_RE = re.compile(r"^[A-Za-z]:[\\/]")
WSL_UNC_PATH_RE = re.compile(r"^\\\\wsl(?:\.localhost)?\\([^\\]+)\\(.*)$", re.IGNORECASE)


def maybe_delegate_to_wsl(argv: list[str] | None = None) -> int | None:
    if not _should_delegate():
        return None

    args = list(sys.argv[1:] if argv is None else argv)
    distro = os.environ.get(WINDOWS_DISTRO_ENV, DEFAULT_DISTRO)
    command = build_wsl_command(args, distro=distro)
    try:
        completed = subprocess.run(command, check=False)
    except FileNotFoundError:
        print(
            "local-n8n on Windows requires WSL. Install WSL with Ubuntu, then rerun lon.",
            file=sys.stderr,
        )
        return 10
    return completed.returncode


def build_wsl_command(args: list[str], *, distro: str = DEFAULT_DISTRO) -> list[str]:
    wsl = _wsl_executable()
    wsl_args = [wsl, "-d", distro]
    wsl_cwd = _wsl_cwd(distro)
    if wsl_cwd is not None:
        wsl_args.extend(["--cd", wsl_cwd])
    wsl_args.append("--exec")

    converted_args = [_to_wsl_arg(arg, distro=distro) for arg in args]
    repo = os.environ.get(WINDOWS_REPO_ENV)
    if repo:
        repo_path = _to_wsl_path(repo, distro=distro)
        return [
            *wsl_args,
            "sh",
            "-lc",
            'cd "$1" && shift && exec uv run lon "$@"',
            "local-n8n-repo",
            repo_path,
            *converted_args,
        ]

    return [
        *wsl_args,
        "sh",
        "-lc",
        _wsl_package_command(),
        "local-n8n",
        os.environ.get(WINDOWS_PACKAGE_SPEC_ENV, "local-n8n"),
        *converted_args,
    ]


def _should_delegate() -> bool:
    if platform.system() != "Windows":
        return False
    if os.environ.get(WINDOWS_INNER_ENV):
        return False
    bridge_setting = os.environ.get(WINDOWS_BRIDGE_ENV, "1").lower()
    return bridge_setting not in DISABLED_VALUES


def _wsl_executable() -> str:
    return shutil.which("wsl.exe") or "wsl.exe"


def _wsl_cwd(distro: str) -> str | None:
    try:
        return _to_wsl_path(str(Path.cwd()), distro=distro)
    except (OSError, RuntimeError):
        return None


def _to_wsl_arg(arg: str, *, distro: str) -> str:
    if arg.startswith("--") and "=" in arg:
        option, value = arg.split("=", 1)
        if _looks_like_windows_path(value) or _looks_like_wsl_unc_path(value):
            try:
                return f"{option}={_to_wsl_path(value, distro=distro)}"
            except RuntimeError:
                return arg

    if _looks_like_windows_path(arg) or _looks_like_wsl_unc_path(arg):
        try:
            return _to_wsl_path(arg, distro=distro)
        except RuntimeError:
            return arg
    return arg


def _to_wsl_path(path: str, *, distro: str) -> str:
    unc_match = WSL_UNC_PATH_RE.match(path)
    if unc_match is not None:
        path_distro = unc_match.group(1)
        if path_distro.lower() != distro.lower():
            raise RuntimeError(
                f"path belongs to WSL distro {path_distro!r}, but target distro is {distro!r}"
            )
        return "/" + unc_match.group(2).replace("\\", "/")

    if _looks_like_windows_path(path):
        completed = subprocess.run(
            [_wsl_executable(), "-d", distro, "--exec", "wslpath", "-a", path],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip() or f"could not convert path: {path}")
        return completed.stdout.strip()

    return path


def _looks_like_windows_path(value: str) -> bool:
    return bool(WINDOWS_ABSOLUTE_PATH_RE.match(value))


def _looks_like_wsl_unc_path(value: str) -> bool:
    return bool(WSL_UNC_PATH_RE.match(value))


def _wsl_package_command() -> str:
    return (
        "export LOCAL_N8N_WINDOWS_BRIDGE_INNER=1; "
        'package_spec="$1"; '
        "shift; "
        "if command -v lon >/dev/null 2>&1; then "
        'exec lon "$@"; '
        "fi; "
        "if command -v uvx >/dev/null 2>&1; then "
        'exec uvx --from "$package_spec" lon "$@"; '
        "fi; "
        "if command -v uv >/dev/null 2>&1; then "
        'exec uv tool run --from "$package_spec" lon "$@"; '
        "fi; "
        "echo 'local-n8n is installed on Windows, but WSL does not have lon or uv available.' >&2; "
        "echo 'Install uv inside WSL, or install local-n8n inside WSL, then rerun lon from "
        "PowerShell.' >&2; "
        "exit 10"
    )
