# Funciones compartidas por los scripts de KAI AI (Windows PowerShell 5.1+ / PowerShell 7+).
# No modifican configuraciones globales del sistema.

$ErrorActionPreference = 'Stop'
$script:RepoRoot = Split-Path -Parent $PSScriptRoot
$script:BackendDir = Join-Path $RepoRoot 'backend'
$script:WebDir = Join-Path $RepoRoot 'apps\web'
$script:VenvPython = Join-Path $BackendDir '.venv\Scripts\python.exe'
$script:DataDir = Join-Path $RepoRoot 'data'
$script:PidFile = Join-Path $DataDir 'kai.pid'

function Write-Step([string]$msg) { Write-Host "==> $msg" -ForegroundColor Cyan }
function Write-Ok([string]$msg) { Write-Host "    OK  $msg" -ForegroundColor Green }
function Write-Warn([string]$msg) { Write-Host "    !!  $msg" -ForegroundColor Yellow }
function Fail([string]$msg) {
    Write-Host ""
    Write-Host "ERROR: $msg" -ForegroundColor Red
    exit 1
}

# Devuelve el comando para ejecutar Python >= 3.11 (py launcher o python), o $null.
function Find-Python {
    $candidates = @(
        @{ Cmd = 'py'; Args = @('-3.13') }, @{ Cmd = 'py'; Args = @('-3.12') }, @{ Cmd = 'py'; Args = @('-3.11') },
        @{ Cmd = 'python'; Args = @() }, @{ Cmd = 'python3'; Args = @() }
    )
    foreach ($c in $candidates) {
        if (-not (Get-Command $c.Cmd -ErrorAction SilentlyContinue)) { continue }
        try {
            $v = & $c.Cmd @($c.Args + @('-c', 'import sys; print("%d.%d" % sys.version_info[:2])')) 2>$null
            if ($LASTEXITCODE -ne 0 -or -not $v) { continue }
            $parts = $v.Trim().Split('.')
            if ([int]$parts[0] -eq 3 -and [int]$parts[1] -ge 11) {
                return @{ Cmd = $c.Cmd; Args = $c.Args; Version = $v.Trim() }
            }
        } catch { continue }
    }
    return $null
}

function Get-NodeVersion {
    if (-not (Get-Command node -ErrorAction SilentlyContinue)) { return $null }
    try { return (& node --version).Trim().TrimStart('v') } catch { return $null }
}

function Test-NodeOk {
    $v = Get-NodeVersion
    if (-not $v) { return $false }
    $p = $v.Split('.')
    $major = [int]$p[0]; $minor = [int]$p[1]
    return ($major -gt 22) -or ($major -eq 22 -and $minor -ge 12) -or ($major -eq 20 -and $minor -ge 19)
}

function Get-KaiPort {
    $port = 8765
    $envFile = Join-Path $RepoRoot '.env'
    if (Test-Path $envFile) {
        $line = Get-Content $envFile | Where-Object { $_ -match '^\s*KAI_PORT\s*=\s*(\d+)' } | Select-Object -First 1
        if ($line -and $line -match '(\d+)') { $port = [int]$Matches[1] }
    }
    return $port
}

function Test-KaiHealth([int]$port) {
    try {
        $r = Invoke-RestMethod -Uri "http://127.0.0.1:$port/api/v1/health" -TimeoutSec 2
        return $r.status -eq 'ok'
    } catch { return $false }
}

function Assert-Installed {
    if (-not (Test-Path $VenvPython)) {
        Fail "KAI no está instalado. Ejecutá primero: scripts\install.ps1"
    }
}
