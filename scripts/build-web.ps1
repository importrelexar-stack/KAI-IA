<#
.SYNOPSIS
  Compila la interfaz web (apps\web) para que KAI Core la sirva en producción.
#>
. "$PSScriptRoot\_common.ps1"

if (-not (Test-NodeOk)) {
    Fail "Se necesita Node.js 20.19+ o 22.12+ (LTS recomendado). Instalalo desde https://nodejs.org o con: winget install OpenJS.NodeJS.LTS"
}

Push-Location $WebDir
try {
    Write-Step "Instalando dependencias de la interfaz (npm ci)"
    if (Test-Path 'package-lock.json') { npm ci --no-fund --no-audit } else { npm install --no-fund --no-audit }
    if ($LASTEXITCODE -ne 0) { Fail "npm no pudo instalar las dependencias." }
    Write-Step "Compilando"
    npm run build
    if ($LASTEXITCODE -ne 0) { Fail "La compilación de la interfaz falló." }
    Write-Ok "Interfaz compilada en apps\web\dist"
} finally {
    Pop-Location
}
