Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Distro = "Ubuntu"
$UseRepo = $false
$WslWorkingDirectory = ""
$LonArgs = @()

for ($index = 0; $index -lt $args.Count; $index++) {
    $arg = [string]$args[$index]
    if ($arg -eq "-Distro") {
        $index++
        if ($index -ge $args.Count) {
            throw "-Distro requires a value."
        }
        $Distro = [string]$args[$index]
        continue
    }
    if ($arg -eq "-UseRepo") {
        $UseRepo = $true
        continue
    }
    if ($arg -eq "-WslWorkingDirectory") {
        $index++
        if ($index -ge $args.Count) {
            throw "-WslWorkingDirectory requires a value."
        }
        $WslWorkingDirectory = [string]$args[$index]
        continue
    }
    if ($arg -eq "--") {
        if ($index + 1 -lt $args.Count) {
            $LonArgs = @($args[($index + 1)..($args.Count - 1)])
        }
        break
    }

    $LonArgs = @($args[$index..($args.Count - 1)])
    break
}

function Test-CommandAvailable {
    param([string]$Name)
    return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

function Convert-ToWslPath {
    param([string]$Path)

    $cleanPath = $Path -replace "^Microsoft\.PowerShell\.Core\\FileSystem::", ""

    if ($cleanPath -match "^\\\\wsl(?:\.localhost)?\\([^\\]+)\\(.*)$") {
        $pathDistro = $Matches[1]
        if ($pathDistro -ne $Distro) {
            throw "Path belongs to WSL distro '$pathDistro', but launcher is targeting '$Distro'."
        }
        return "/" + ($Matches[2] -replace "\\", "/")
    }

    if ($cleanPath -match "^[A-Za-z]:\\") {
        $converted = & wsl.exe -d $Distro --exec wslpath -a $cleanPath
        if ($LASTEXITCODE -ne 0) {
            throw "Could not convert Windows path to WSL path: $cleanPath"
        }
        return ($converted | Select-Object -First 1).Trim()
    }

    return $cleanPath
}

if (-not (Test-CommandAvailable "wsl.exe")) {
    throw "wsl.exe was not found. Run this script from Windows PowerShell or Windows Terminal."
}

if ($null -eq $LonArgs -or $LonArgs.Count -eq 0) {
    $LonArgs = @("--help")
}

if ($UseRepo -and [string]::IsNullOrWhiteSpace($WslWorkingDirectory)) {
    $repoRoot = Split-Path -Parent $PSScriptRoot
    $WslWorkingDirectory = Convert-ToWslPath $repoRoot
}

$wslArgs = @("-d", $Distro)
if (-not [string]::IsNullOrWhiteSpace($WslWorkingDirectory)) {
    $wslArgs += @("--cd", $WslWorkingDirectory)
}
$wslArgs += @("--exec")

$command = if ($UseRepo) {
    @("uv", "run", "lon")
} else {
    @("lon")
}

& wsl.exe @wslArgs @command @LonArgs
exit $LASTEXITCODE
