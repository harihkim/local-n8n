[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Write-Info {
    param([string]$Message)
    Write-Host "    $Message"
}

function Test-CommandAvailable {
    param([string]$Name)
    return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

Write-Step "local-n8n Windows prerequisites"
Write-Info "Run local-n8n from Windows PowerShell. WSL is not required for normal use."

if (-not (Test-CommandAvailable "docker")) {
    Write-Step "Docker CLI was not found"
    Write-Info "Install Docker Desktop for Windows, start it, then open a new PowerShell window."
    Write-Info "After that, run: lon doctor"
    exit 10
}

Write-Step "Docker CLI"
docker --version

Write-Step "Docker daemon"
docker info *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Info "Docker CLI is installed, but Docker Desktop does not appear to be running."
    Write-Info "Start Docker Desktop, then run: lon doctor"
    exit 10
}
Write-Info "Docker daemon is reachable."

Write-Step "Docker Compose"
docker compose version
if ($LASTEXITCODE -ne 0) {
    Write-Info "Docker Compose is unavailable. Repair or update Docker Desktop, then run: lon doctor"
    exit 10
}

Write-Step "local-n8n"
Write-Info "Prerequisites look ready. Run:"
Write-Host ""
Write-Host "    lon doctor"
Write-Host "    lon init"
