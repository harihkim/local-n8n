# Windows Setup

On Windows, use PowerShell as the main interface. `local-n8n` still runs the Linux `lon` command inside WSL
Ubuntu, but the Windows launcher handles that bridge so you do not need to type routine commands in an
Ubuntu shell.

The intended Windows command is still:

```powershell
lon init
```

When installed as a package on Windows, the `lon` entrypoint delegates commands into WSL automatically.

## Recommended Path

For most users, use Docker Desktop with WSL integration:

1. Install or enable WSL 2 with Ubuntu.
2. Install Docker Desktop for Windows.
3. Start Docker Desktop.
4. Enable the WSL 2 based engine.
5. Enable Docker Desktop WSL integration for the Ubuntu distro.
6. Install `local-n8n` with `uv` or `pipx`.
7. From PowerShell, run `lon doctor`.

This keeps Docker daemon management on the Windows side while `lon` and n8n project files stay in Linux.
The PowerShell launcher runs `lon` inside WSL for you.

## Package Install

After PyPI publishing is enabled:

```powershell
uv tool install local-n8n
lon doctor
lon init
```

`pipx` is also a good fit for CLI installation:

```powershell
pipx install local-n8n
lon doctor
lon init
```

During alpha releases before PyPI publishing, install from the tagged GitHub prerelease and tell the Windows
bridge to use the same package source inside WSL:

```powershell
uv tool install git+https://github.com/harihkim/local-n8n.git@v0.1.0a3
$env:LOCAL_N8N_WINDOWS_PACKAGE_SPEC = "git+https://github.com/harihkim/local-n8n.git@v0.1.0a3"
lon doctor
```

Set `LOCAL_N8N_WINDOWS_PACKAGE_SPEC` as a user environment variable if you want that alpha git source to
persist across PowerShell sessions.

## Alternative Path

Advanced users can install Docker Engine directly inside WSL instead of using Docker Desktop.

Do not use both Docker Desktop WSL integration and a separate Docker Engine inside the same WSL distro at
the same time.

From PowerShell, run the install/repair commands through the installed Windows `lon` command:

```powershell
lon --dry-run doctor --fix
lon doctor --fix
```

## Bootstrap Helper

The helper script lives in the source repository and is useful when setting up from a checkout.

From Windows PowerShell at the repository root:

```powershell
.\scripts\bootstrap-windows.ps1
```

The default mode prepares WSL Ubuntu and prints the Docker Desktop WSL integration steps.

For source-checkout development, install a local Windows `lon` command:

```powershell
.\scripts\install-windows-launcher.ps1
```

That installs a user-local `lon.cmd` shim under `%LOCALAPPDATA%\Programs\local-n8n\bin` and adds that
directory to your user PATH. The shim runs this checkout through WSL with `uv run lon`.

To choose direct Docker Engine inside WSL:

```powershell
.\scripts\bootstrap-windows.ps1 -DockerMode Engine
```

To preview actions without changing WSL state:

```powershell
.\scripts\bootstrap-windows.ps1 -DryRun
```

## Verification

From PowerShell, verify the `lon` view of Docker:

```powershell
lon doctor
```

On Windows, `lon doctor` delegates into WSL. In package mode it runs the installed WSL `lon` when present,
or uses `uv` inside WSL to run the configured package source. In source-checkout mode it runs `uv run lon`
from this checkout.

If you need lower-level Docker details, you can still use Ubuntu directly:

```bash
docker info
docker compose version
lon doctor
```

If `lon doctor` reports Docker Desktop WSL integration as active, that is a supported Windows setup.

## Daily Use

From PowerShell at the repository root:

```powershell
lon init
lon status
lon backup
```

The lower-level launcher is still available for development:

```powershell
.\scripts\lon.ps1 -UseRepo doctor
```
