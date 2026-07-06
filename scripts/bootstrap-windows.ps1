[CmdletBinding()]
param(
    [ValidateSet("Desktop", "Engine")]
    [string]$DockerMode = "Desktop",

    [string]$Distro = "Ubuntu",

    [switch]$DryRun
)

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

function Invoke-StepCommand {
    param(
        [string]$Description,
        [string[]]$Command
    )

    Write-Step $Description
    Write-Info ($Command -join " ")
    if ($DryRun) {
        return
    }

    & $Command[0] $Command[1..($Command.Count - 1)]
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $($Command -join ' ')"
    }
}

function Test-CommandAvailable {
    param([string]$Name)
    return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

function Get-WslDistros {
    if (-not (Test-CommandAvailable "wsl.exe")) {
        return @()
    }

    $raw = & wsl.exe --list --quiet 2>$null
    if ($LASTEXITCODE -ne 0) {
        return @()
    }

    return @(
        $raw |
            ForEach-Object { ($_ -replace "`0", "").Trim() } |
            Where-Object { $_.Length -gt 0 }
    )
}

function Test-WslReady {
    if (-not (Test-CommandAvailable "wsl.exe")) {
        return $false
    }

    & wsl.exe --status *> $null
    return $LASTEXITCODE -eq 0
}

function Ensure-WslDistro {
    if (-not (Test-CommandAvailable "wsl.exe")) {
        throw "wsl.exe was not found. Run this script from Windows PowerShell or Windows Terminal."
    }

    if (-not (Test-WslReady)) {
        Invoke-StepCommand "Install WSL distro" @("wsl.exe", "--install", "-d", $Distro)
        Write-Step "WSL install may need a restart"
        Write-Info "If Windows asks you to reboot, restart and run this script again."
        Write-Info "After first launch, create the Linux user requested by $Distro."
        return
    }

    Invoke-StepCommand "Set WSL 2 as the default version" @("wsl.exe", "--set-default-version", "2")

    $distros = Get-WslDistros
    if ($distros -contains $Distro) {
        Write-Step "WSL distro is already installed"
        Write-Info "$Distro is present."
        return
    }

    Invoke-StepCommand "Install WSL distro" @("wsl.exe", "--install", "-d", $Distro)

    Write-Step "WSL install may need a restart"
    Write-Info "If Windows asks you to reboot, restart and run this script again."
    Write-Info "After first launch, create the Linux user requested by $Distro."
}

function Show-DesktopNextSteps {
    Write-Step "Use Docker Desktop with WSL integration"
    Write-Info "This is the recommended Windows path for most users."
    Write-Info "Install Docker Desktop for Windows if it is not installed."
    Write-Info "Start Docker Desktop."
    Write-Info "Open Settings > General and make sure the WSL 2 based engine is enabled."
    Write-Info "Open Settings > Resources > WSL Integration and enable integration for $Distro."
    Write-Info "Apply the change, then install the Windows lon command:"
    Write-Host ""
    Write-Host "    .\scripts\install-windows-launcher.ps1"
    Write-Host ""
    Write-Info "Then stay in PowerShell and run:"
    Write-Host ""
    Write-Host "    lon doctor"
    Write-Host "    lon init"
    Write-Host ""
    Write-Info "The launcher runs lon inside WSL for you."
}

function Show-EngineNextSteps {
    Write-Step "Use Docker Engine directly inside WSL"
    Write-Info "This avoids Docker Desktop, but Docker runs inside the Linux distro."
    Write-Info "After WSL is ready, install the Windows lon command:"
    Write-Host ""
    Write-Host "    .\scripts\install-windows-launcher.ps1"
    Write-Host ""
    Write-Info "Then stay in PowerShell and run:"
    Write-Host ""
    Write-Host "    lon --dry-run doctor --fix"
    Write-Host "    lon doctor --fix"
    Write-Host "    lon doctor"
    Write-Host ""
    Write-Info "Do not also enable Docker Desktop integration for this distro; using both can conflict."
}

Write-Step "local-n8n Windows bootstrap"
Write-Info "Runtime model: run lon inside WSL $Distro."
Write-Info "Docker mode: $DockerMode"

Ensure-WslDistro

if ($DockerMode -eq "Desktop") {
    Show-DesktopNextSteps
} else {
    Show-EngineNextSteps
}

Write-Step "Done"
Write-Info "After Docker works inside WSL, continue with the local-n8n quickstart."
