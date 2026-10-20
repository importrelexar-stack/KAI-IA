# Funciones compartidas por los scripts de KAI AI (Windows PowerShell 5.1+ / PowerShell 7+).
# No modifican configuraciones globales del sistema.

$ErrorActionPreference = 'Stop'
$script:RepoRoot = Split-Path -Parent $PSScriptRoot
$script:BackendDir = Join-Path $RepoRoot 'backend'
$script:WebDir = Join-Path $RepoRoot 'apps\web'
$script:VenvPython = Join-Path $BackendDir '.venv\Scripts\python.exe'
$script:DataDir = Join-Path $RepoRoot 'data'
$script:PidFile = Join-Path $DataDir 'kai.pid'

# Python con salida UTF-8 (evita errores de codificación en la consola de Windows).
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'

# Ejecuta un programa externo sin que sus avisos por stderr (pip, npm) se conviertan en errores
# terminales de PowerShell 5.1. El resultado se evalúa con $LASTEXITCODE.
function Invoke-Native([scriptblock]$Block) {
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { & $Block } finally { $ErrorActionPreference = $prev }
}

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
        @{ Cmd = 'py'; Args = @('-3') }, @{ Cmd = 'python'; Args = @() }, @{ Cmd = 'python3'; Args = @() }
    )
    foreach ($c in $candidates) {
        if (-not (Get-Command $c.Cmd -ErrorAction SilentlyContinue)) { continue }
        try {
            $v = Invoke-Native { & $c.Cmd @($c.Args + @('-c', 'import sys; print("%d.%d" % sys.version_info[:2])')) 2>$null }
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
    try { return (Invoke-Native { & node --version }).ToString().Trim().TrimStart('v') } catch { return $null }
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

# URL del repositorio en GitHub (para descargar la interfaz precompilada).
function Get-RepoSlug {
    $default = 'importrelexar-stack/KAI-IA'
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) { return $default }
    $url = Invoke-Native { & git -C $RepoRoot remote get-url origin 2>$null }
    if ($LASTEXITCODE -eq 0 -and $url -and ($url.ToString() -match 'github\.com[:/]([^/]+/[^/.]+?)(\.git)?$')) { return $Matches[1] }
    return $default
}

# Descarga la interfaz compilada por GitHub Actions (release "web-latest"). No instala software.
function Install-PrebuiltWeb {
    $slug = Get-RepoSlug
    $url = "https://github.com/$slug/releases/download/web-latest/kai-web-dist.zip"
    $zip = Join-Path $env:TEMP 'kai-web-dist.zip'
    $dist = Join-Path $WebDir 'dist'
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing
        if (Test-Path $dist) { Remove-Item $dist -Recurse -Force }
        Expand-Archive -Path $zip -DestinationPath $dist -Force
        Remove-Item $zip -ErrorAction SilentlyContinue
        return (Test-Path (Join-Path $dist 'index.html'))
    } catch {
        Write-Warn "No se pudo descargar la interfaz precompilada ($url): $($_.Exception.Message)"
        return $false
    }
}
