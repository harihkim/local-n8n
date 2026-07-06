# Windows Setup

On Windows, run `lon` inside WSL Ubuntu. The Windows host provides WSL, and Docker must be available inside
that WSL distro.

## Recommended Path

For most users, use Docker Desktop with WSL integration:

1. Install or enable WSL 2 with Ubuntu.
2. Install Docker Desktop for Windows.
3. Start Docker Desktop.
4. Enable the WSL 2 based engine.
5. Enable Docker Desktop WSL integration for the Ubuntu distro.
6. Open Ubuntu and run `lon doctor`.

This keeps Docker daemon management on the Windows side while `lon` and n8n project files stay in Linux.

## Alternative Path

Advanced users can install Docker Engine directly inside WSL instead of using Docker Desktop:

```bash
lon --dry-run doctor --fix
lon doctor --fix
```

Do not use both Docker Desktop WSL integration and a separate Docker Engine inside the same WSL distro at
the same time.

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

Inside Ubuntu, verify Docker before starting n8n:

```bash
docker info
docker compose version
lon doctor
```

If `lon doctor` reports Docker Desktop WSL integration as active, that is a supported Windows setup.
