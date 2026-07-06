# Windows Setup

On Windows, use PowerShell as the main interface. `local-n8n` still runs the Linux `lon` command inside WSL
Ubuntu, but the Windows launcher handles that bridge so you do not need to type routine commands in an
Ubuntu shell.

The intended Windows command is still:

```powershell
lon init
```

The Windows installer below creates that command by installing a small `lon.cmd` shim on your user PATH.

## Recommended Path

For most users, use Docker Desktop with WSL integration:

1. Install or enable WSL 2 with Ubuntu.
2. Install Docker Desktop for Windows.
3. Start Docker Desktop.
4. Enable the WSL 2 based engine.
5. Enable Docker Desktop WSL integration for the Ubuntu distro.
6. Install the Windows `lon` command with `.\scripts\install-windows-launcher.ps1`.
7. From PowerShell, run `lon doctor`.

This keeps Docker daemon management on the Windows side while `lon` and n8n project files stay in Linux.
The PowerShell launcher runs `lon` inside WSL for you.

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

Then install the Windows `lon` command:

```powershell
.\scripts\install-windows-launcher.ps1
```

That installs a user-local `lon.cmd` shim under `%LOCALAPPDATA%\Programs\local-n8n\bin` and adds that
directory to your user PATH.

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

In repository mode, that command runs `uv run lon doctor` inside WSL from this checkout.

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
