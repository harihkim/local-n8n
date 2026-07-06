# Windows Setup

On Windows, use PowerShell as the main interface. `local-n8n` still runs the Linux `lon` command inside WSL
Ubuntu, but the Windows launcher handles that bridge so you do not need to type routine commands in an
Ubuntu shell.

## Recommended Path

For most users, use Docker Desktop with WSL integration:

1. Install or enable WSL 2 with Ubuntu.
2. Install Docker Desktop for Windows.
3. Start Docker Desktop.
4. Enable the WSL 2 based engine.
5. Enable Docker Desktop WSL integration for the Ubuntu distro.
6. From PowerShell, run `.\scripts\lon.ps1 -UseRepo doctor`.

This keeps Docker daemon management on the Windows side while `lon` and n8n project files stay in Linux.
The PowerShell launcher runs `lon` inside WSL for you.

## Alternative Path

Advanced users can install Docker Engine directly inside WSL instead of using Docker Desktop.

Do not use both Docker Desktop WSL integration and a separate Docker Engine inside the same WSL distro at
the same time.

From PowerShell, run the install/repair commands through the Windows launcher:

```powershell
.\scripts\lon.ps1 -UseRepo --dry-run doctor --fix
.\scripts\lon.ps1 -UseRepo doctor --fix
```

## Bootstrap Helper

The helper script lives in the source repository and is useful when setting up from a checkout.

From Windows PowerShell at the repository root:

```powershell
.\scripts\bootstrap-windows.ps1
```

The default mode prepares WSL Ubuntu and prints the Docker Desktop WSL integration steps.

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
.\scripts\lon.ps1 -UseRepo doctor
```

That command runs `uv run lon doctor` inside WSL from this checkout.

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
.\scripts\lon.ps1 -UseRepo init
.\scripts\lon.ps1 -UseRepo status
.\scripts\lon.ps1 -UseRepo backup
```

After `local-n8n` is installed inside WSL as a normal tool, omit `-UseRepo`:

```powershell
.\scripts\lon.ps1 doctor
.\scripts\lon.ps1 init
```
