<#
.SYNOPSIS
  Ejecuta las pruebas automatizadas (backend con pytest y, si hay Node.js, frontend con Vitest).
  No usa claves reales: el proveedor de IA está simulado.
#>
. "$PSScriptRoot\_common.ps1"
Assert-Installed

Write-Step "Pruebas del backend"
& $VenvPython -m pip install --disable-pip-version-check -q -r (Join-Path $BackendDir 'requirements-dev.txt')
Push-Location $BackendDir
try {
    $env:ANTHROPIC_API_KEY = ''
    & $VenvPython -m pytest
    $backendCode = $LASTEXITCODE
} finally { Pop-Location }

$webCode = 0
if (Test-NodeOk) {
    Write-Step "Pruebas y verificación de tipos del frontend"
    Push-Location $WebDir
    try {
        if (-not (Test-Path 'node_modules')) { npm ci --no-fund --no-audit }
        npm run typecheck; if ($LASTEXITCODE -ne 0) { $webCode = 1 }
        npm test; if ($LASTEXITCODE -ne 0) { $webCode = 1 }
    } finally { Pop-Location }
} else {
    Write-Warn "Node.js no está instalado: se omiten las pruebas del frontend."
}

if ($backendCode -ne 0 -or $webCode -ne 0) { Fail "Hay pruebas fallidas." }
Write-Ok "Todas las pruebas ejecutadas pasaron."
