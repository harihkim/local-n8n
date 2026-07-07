# Windows Setup

On Windows, use PowerShell as the main interface. `local-n8n` runs as a normal Windows-installed Python CLI
and talks to Docker Desktop for Windows.

WSL is not required for normal Windows use.

## Install

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

During alpha releases before PyPI publishing, install from the tagged GitHub prerelease:

```powershell
uv tool install git+https://github.com/harihkim/local-n8n.git@v0.1.0a3
lon doctor
lon init
```

From a source checkout:

```powershell
uv run lon --help
uv run lon doctor
```

## Docker Desktop

Install Docker Desktop for Windows and start it before running `lon init`.

Expected checks:

```powershell
docker info
docker compose version
lon doctor
```

`lon doctor` should report:

- Windows platform
- Docker CLI available
- Docker daemon reachable
- Docker Desktop backend active
- Docker Compose available
- target port available

## Optional Helper

From a source checkout, this helper checks the Windows Docker prerequisites and prints the next native
PowerShell commands:

```powershell
.\scripts\check-windows-prereqs.ps1
```

The helper does not install WSL and does not route normal `lon` usage through WSL.

## Daily Use

From PowerShell:

```powershell
lon init
lon status
lon backup
lon restore C:\Users\you\Backups\default.n8nbundle
```

By default, local files and diagnostic logs are stored under:

```text
%LOCALAPPDATA%\local-n8n\
```
