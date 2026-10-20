<#
.SYNOPSIS
  Instala KAI AI en este equipo (Windows): entorno virtual de Python, dependencias y archivo .env.

.DESCRIPTION
  - No instala programas por su cuenta ni cambia configuraciones globales.
  - Si falta Python 3.11+ o Node.js, explica cómo instalarlos.
  - Node.js sólo es necesario para compilar la interfaz web.

.PARAMETER Dev
  Instala también las dependencias de desarrollo y pruebas.

.PARAMETER NoVoice
  No instala los motores de voz locales (Whisper y Piper). KAI usará la voz del navegador.
#>
param([switch]$Dev, [switch]$NoVoice)

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
    Invoke-Native { & $py.Cmd @($py.Args + @('-m', 'venv', (Join-Path $BackendDir '.venv'))) }
    if ($LASTEXITCODE -ne 0) { Fail "No se pudo crear el entorno virtual." }
    Write-Ok "Entorno virtual creado"
} else {
    Write-Ok "Ya existía"
}

# 3. Dependencias
Write-Step "Instalando dependencias de Python"
$req = if ($Dev) { 'requirements-dev.txt' } else { 'requirements.txt' }
Invoke-Native { & $VenvPython -m pip install --disable-pip-version-check -q --upgrade pip }
Invoke-Native { & $VenvPython -m pip install --disable-pip-version-check -q -r (Join-Path $BackendDir $req) }
if ($LASTEXITCODE -ne 0) { Fail "Falló la instalación de dependencias. Revisá tu conexión a Internet y reintentá." }
Write-Ok "Dependencias instaladas ($req)"

# 3b. Voz local (opcional: si falla, KAI sigue funcionando con la voz del navegador)
if (-not $NoVoice) {
    Write-Step "Instalando motores de voz locales (Whisper + Piper, ~150 MB)"
    Invoke-Native { & $VenvPython -m pip install --disable-pip-version-check -q -r (Join-Path $BackendDir 'requirements-voice.txt') }
    if ($LASTEXITCODE -eq 0) {
        Write-Ok "Voz local instalada. Los modelos se descargan desde la pantalla Voz cuando lo decidas."
    } else {
        Write-Warn "No se pudieron instalar los motores de voz locales. KAI usará la voz del navegador."
    }
}

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
    Write-Warn "No se encontró Node.js: se descarga la interfaz ya compilada desde GitHub."
    if (Install-PrebuiltWeb) {
        Write-Ok "Interfaz descargada en apps\web\dist"
    } else {
        Write-Warn "Para compilarla vos: instalá Node.js LTS (https://nodejs.org o winget install OpenJS.NodeJS.LTS)"
        Write-Warn "y ejecutá scripts\build-web.ps1. Mientras tanto la API queda en http://127.0.0.1:8765/docs"
    }
}

# 6. Acceso directo
if (-not $NoShortcut) {
    Write-Step "Acceso directo en el escritorio"
    try {
        & "$PSScriptRoot\create-shortcut.ps1"
    } catch {
        Write-Warn "No se pudo crear el acceso directo: $($_.Exception.Message). Podés crearlo después con crear-acceso-directo.bat"
    }
}

Write-Host ""
Write-Host "Instalación terminada." -ForegroundColor Green
Write-Host "  1. (Opcional) Poné tu clave en .env (ANTHROPIC_API_KEY) o cargala luego desde Configuración."
Write-Host "  2. Iniciá KAI con el acceso directo «KAI AI» del escritorio (o doble clic en start.bat)"
Write-Host ""
