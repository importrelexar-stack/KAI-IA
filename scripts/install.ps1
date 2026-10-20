<#
.SYNOPSIS
  Instala KAI AI en este equipo (Windows): entorno virtual de Python, dependencias y archivo .env.

.DESCRIPTION
  - No instala programas por su cuenta ni cambia configuraciones globales.
  - Si falta Python 3.11+ o Node.js, explica cómo instalarlos.
  - Node.js sólo es necesario para compilar la interfaz web.

.PARAMETER Dev
  Instala también las dependencias de desarrollo y pruebas.
#>
param([switch]$Dev)

. "$PSScriptRoot\_common.ps1"

Write-Host ""
Write-Host "  KAI AI — instalación" -ForegroundColor White
Write-Host ""

# 1. Python
Write-Step "Buscando Python 3.11 o superior"
$py = Find-Python
if (-not $py) {
    Fail @"
No se encontró Python 3.11+.
Instalalo desde https://www.python.org/downloads/windows/ (marcá 'Add python.exe to PATH')
o con winget:   winget install Python.Python.3.13
Después cerrá y volvé a abrir la terminal y ejecutá de nuevo este script.
"@
}
Write-Ok "Python $($py.Version) ($($py.Cmd) $($py.Args -join ' '))"

# 2. Entorno virtual
Write-Step "Creando entorno virtual en backend\.venv"
if (-not (Test-Path $VenvPython)) {
    & $py.Cmd @($py.Args + @('-m', 'venv', (Join-Path $BackendDir '.venv')))
    if ($LASTEXITCODE -ne 0) { Fail "No se pudo crear el entorno virtual." }
    Write-Ok "Entorno virtual creado"
} else {
    Write-Ok "Ya existía"
}

# 3. Dependencias
Write-Step "Instalando dependencias de Python"
$req = if ($Dev) { 'requirements-dev.txt' } else { 'requirements.txt' }
& $VenvPython -m pip install --disable-pip-version-check -q --upgrade pip
& $VenvPython -m pip install --disable-pip-version-check -q -r (Join-Path $BackendDir $req)
if ($LASTEXITCODE -ne 0) { Fail "Falló la instalación de dependencias. Revisá tu conexión a Internet y reintentá." }
Write-Ok "Dependencias instaladas ($req)"

# 4. .env
Write-Step "Configuración"
$envFile = Join-Path $RepoRoot '.env'
if (-not (Test-Path $envFile)) {
    Copy-Item (Join-Path $RepoRoot '.env.example') $envFile
    Write-Ok "Se creó .env a partir de .env.example"
} else {
    Write-Ok ".env ya existe (no se modificó)"
}
New-Item -ItemType Directory -Force -Path $DataDir | Out-Null

# 5. Interfaz web
Write-Step "Interfaz web"
$dist = Join-Path $WebDir 'dist\index.html'
if (Test-Path $dist) {
    Write-Ok "Interfaz ya compilada"
} elseif (Test-NodeOk) {
    Write-Ok "Node.js $(Get-NodeVersion) detectado. Compilando la interfaz…"
    & "$PSScriptRoot\build-web.ps1"
} else {
    Write-Warn "No se encontró Node.js 20.19+ / 22.12+. Es necesario sólo para compilar la interfaz."
    Write-Warn "Instalalo desde https://nodejs.org (versión LTS) o con: winget install OpenJS.NodeJS.LTS"
    Write-Warn "Luego ejecutá: scripts\build-web.ps1"
    Write-Warn "Mientras tanto KAI Core funciona y su API queda en http://127.0.0.1:8765/docs"
}

Write-Host ""
Write-Host "Instalación terminada." -ForegroundColor Green
Write-Host "  1. (Opcional) Poné tu clave en .env (ANTHROPIC_API_KEY) o cargala luego desde Configuración."
Write-Host "  2. Iniciá KAI con:  scripts\start.ps1   (o doble clic en start.bat)"
Write-Host ""
