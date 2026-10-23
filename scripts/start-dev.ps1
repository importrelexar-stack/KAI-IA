<#
.SYNOPSIS
  Modo desarrollo: KAI Core con recarga automática (puerto 8765) + Vite (puerto 5173), cada uno en su ventana.

.PARAMETER Demo
  Inicia el backend en modo demostración (sin IA).
#>
param([switch]$Demo)

. "$PSScriptRoot\_common.ps1"
Assert-Installed

$shell = if (Get-Command pwsh -ErrorAction SilentlyContinue) { 'pwsh' } else { 'powershell' }
$demoCmd = if ($Demo) { "`$env:KAI_DEMO_MODE='true'; " } else { '' }

Write-Step "Iniciando KAI Core (recarga automática) en http://127.0.0.1:8765"
$backendCmd = "${demoCmd}Set-Location '$BackendDir'; & '$VenvPython' -m uvicorn app.main:create_app --factory --reload --host 127.0.0.1 --port 8765"
Start-Process $shell -ArgumentList @('-NoExit', '-Command', $backendCmd)

if (Test-NodeOk) {
    if (-not (Test-Path (Join-Path $WebDir 'node_modules'))) {
        Write-Step "Instalando dependencias de la interfaz"
        Push-Location $WebDir; Invoke-Native { npm install --no-fund --no-audit }; Pop-Location
    }
    Write-Step "Iniciando la interfaz (Vite) en http://127.0.0.1:5173"
    Start-Process $shell -ArgumentList @('-NoExit', '-Command', "Set-Location '$WebDir'; npm run dev")
    Start-Sleep -Seconds 3
    Start-Process "http://127.0.0.1:5173"
} else {
    Write-Warn "Node.js no está instalado: sólo se inició el backend (API en http://127.0.0.1:8765/docs)."
}
Write-Ok "Para detener el modo desarrollo, cerrá ambas ventanas o presioná Ctrl+C en cada una."
