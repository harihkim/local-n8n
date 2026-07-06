[CmdletBinding()]
param(
    [string]$Distro = "Ubuntu",

    [ValidateSet("Repo", "Tool")]
    [string]$Mode = "Repo",

    [string]$InstallDir = "$env:LOCALAPPDATA\Programs\local-n8n\bin",

    [switch]$Force
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

function Convert-ToCmdLiteral {
    param([string]$Value)
    return '"' + ($Value -replace '"', '\"') + '"'
}

function Add-UserPath {
    param([string]$PathToAdd)

    $currentUserPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $entries = @()
    if (-not [string]::IsNullOrWhiteSpace($currentUserPath)) {
        $entries = @($currentUserPath -split ";" | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    }

    if ($entries -notcontains $PathToAdd) {
        $nextUserPath = (@($entries) + $PathToAdd) -join ";"
        [Environment]::SetEnvironmentVariable("Path", $nextUserPath, "User")
    }

    $sessionEntries = @($env:Path -split ";" | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    if ($sessionEntries -notcontains $PathToAdd) {
        $env:Path = (@($sessionEntries) + $PathToAdd) -join ";"
    }
}

if (-not $env:LOCALAPPDATA) {
    throw "LOCALAPPDATA is not set. Run this script from Windows PowerShell."
}

$sourceLauncher = Join-Path $PSScriptRoot "lon.ps1"
if (-not (Test-Path $sourceLauncher)) {
    throw "Could not find source launcher: $sourceLauncher"
}

$repoRoot = Split-Path -Parent $PSScriptRoot
$installPath = [System.IO.Path]::GetFullPath($InstallDir)
$targetLauncher = Join-Path $installPath "lon-wsl.ps1"
$targetCommand = Join-Path $installPath "lon.cmd"

Write-Step "Install local-n8n Windows launcher"
Write-Info "Install directory: $installPath"
Write-Info "WSL distro: $Distro"
Write-Info "Mode: $Mode"

New-Item -ItemType Directory -Force -Path $installPath | Out-Null

if ((Test-Path $targetCommand) -and -not $Force) {
    throw "Launcher already exists: $targetCommand. Re-run with -Force to replace it."
}

Copy-Item -Force $sourceLauncher $targetLauncher

$cmdArgs = @("-Distro", (Convert-ToCmdLiteral $Distro))
if ($Mode -eq "Repo") {
    $cmdArgs += @("-UseRepo", "-WslWorkingDirectory", (Convert-ToCmdLiteral $repoRoot))
}
$cmdArgsText = $cmdArgs -join " "

$cmdContent = @"
@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0lon-wsl.ps1" $cmdArgsText %*
exit /b %ERRORLEVEL%
"@

Set-Content -Path $targetCommand -Value $cmdContent -Encoding ASCII
Add-UserPath $installPath

Write-Step "Installed"
Write-Info "You can now run local-n8n from PowerShell:"
Write-Host ""
Write-Host "    lon doctor"
Write-Host "    lon init"
Write-Host ""
if ($Mode -eq "Repo") {
    Write-Info "This launcher runs the checkout through WSL with: uv run lon"
} else {
    Write-Info "This launcher expects lon to already be installed inside WSL."
}
Write-Info "Open a new PowerShell window if the current shell does not pick up PATH immediately."
