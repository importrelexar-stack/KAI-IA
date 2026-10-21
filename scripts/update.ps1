<#
.SYNOPSIS
  Actualiza una instalación de KAI AI hecha desde el código: detiene KAI, trae la última versión con git
  (sin descartar cambios locales) y vuelve a instalar las dependencias.

.DESCRIPTION
  - Si hay archivos modificados en la carpeta, no actualiza y lo explica (nunca los pisa).
  - Sólo hace «git pull --ff-only» de la rama actual: no reescribe historial.
  - Tus datos (carpeta data\ y la clave en el Administrador de credenciales) no se tocan.
#>
. "$PSScriptRoot\_common.ps1"

Set-Location $RepoRoot
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Fail "No se encontró git. Si descargaste KAI como .zip, bajá la versión nueva o usá el instalador Instalar-KAI-AI.exe."
}
if (-not (Test-Path (Join-Path $RepoRoot '.git'))) {
    Fail "Esta carpeta no es un clon de git. Usá el instalador Instalar-KAI-AI.exe para actualizar."
}

Write-Step "Buscando cambios locales"
$dirty = Invoke-Native { git status --porcelain --untracked-files=no }
if ($dirty) {
    Write-Warn "Hay archivos modificados en la carpeta de KAI:"
    $dirty | ForEach-Object { Write-Host "      $_" }
    Fail "No se actualizó para no pisar tus cambios. Guardalos o descartalos y volvé a ejecutar actualizar.bat."
}
Write-Ok "Sin cambios locales"

Write-Step "Deteniendo KAI"
& "$PSScriptRoot\stop.ps1"

Write-Step "Descargando la última versión"
Invoke-Native { git pull --ff-only }
if ($LASTEXITCODE -ne 0) { Fail "git pull falló (¿sin Internet?). KAI quedó en la versión anterior." }
Write-Ok "Código actualizado"

Write-Step "Reinstalando dependencias"
& "$PSScriptRoot\install.ps1" -NoShortcut
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host ""
Write-Ok "KAI quedó actualizado. Abrilo con start.bat o con el acceso «KAI AI» del escritorio."
