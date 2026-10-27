<#
.SYNOPSIS
  Ejecuta las pruebas automatizadas (backend con pytest y, si hay Node.js, frontend con Vitest).
  No usa claves reales: el proveedor de IA está simulado.
#>
. "$PSScriptRoot\_common.ps1"
Assert-Installed

Write-Step "Pruebas del backend"
Invoke-Native { & $VenvPython -m pip install --disable-pip-version-check -q -r (Join-Path $BackendDir 'requirements-dev.txt') }
Push-Location $BackendDir
try {
    $env:ANTHROPIC_API_KEY = ''
    Invoke-Native { & $VenvPython -m pytest }
    $backendCode = $LASTEXITCODE
} finally { Pop-Location }

$webCode = 0
if (Test-NodeOk) {
    Write-Step "Pruebas y verificación de tipos del frontend"
    Push-Location $WebDir
    try {
        if (-not (Test-Path 'node_modules')) { Invoke-Native { npm ci --no-fund --no-audit } }
        Invoke-Native { npm run typecheck }; if ($LASTEXITCODE -ne 0) { $webCode = 1 }
        Invoke-Native { npm test }; if ($LASTEXITCODE -ne 0) { $webCode = 1 }
    } finally { Pop-Location }
} else {
    Write-Warn "Node.js no está instalado: se omiten las pruebas del frontend."
}

if ($backendCode -ne 0 -or $webCode -ne 0) { Fail "Hay pruebas fallidas." }
Write-Ok "Todas las pruebas ejecutadas pasaron."
