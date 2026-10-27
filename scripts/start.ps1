<#
.SYNOPSIS
  Inicia KAI AI (modo producción): KAI Core sirve la API y la interfaz en http://127.0.0.1:8765

.PARAMETER Demo
  Inicia en modo demostración (sin IA; las respuestas se marcan como DEMOSTRACIÓN).

.PARAMETER NoBrowser
  No abre el navegador automáticamente.
#>
param([switch]$Demo, [switch]$NoBrowser)

. "$PSScriptRoot\_common.ps1"
Assert-Installed

$port = Get-KaiPort
if (Test-KaiHealth $port) {
    Write-Ok "KAI ya está en ejecución en http://127.0.0.1:$port"
    if (-not $NoBrowser) { Start-Process "http://127.0.0.1:$port" }
    exit 0
}

if (-not (Test-Path (Join-Path $WebDir 'dist\index.html'))) {
    Write-Warn "La interfaz no está compilada: intentando descargarla ya compilada…"
    if (-not (Install-PrebuiltWeb)) {
        Write-Warn "Sin interfaz (ejecutá scripts\build-web.ps1). Sólo estará disponible la API en /docs."
    }
}

New-Item -ItemType Directory -Force -Path (Join-Path $DataDir 'logs') | Out-Null
if ($Demo) { $env:KAI_DEMO_MODE = 'true' }

Write-Step "Iniciando KAI Core en http://127.0.0.1:$port"
$stdout = Join-Path $DataDir 'logs\server.out.log'
$stderr = Join-Path $DataDir 'logs\server.err.log'
$proc = Start-Process -FilePath $VenvPython -ArgumentList @('-m', 'app.main') -WorkingDirectory $BackendDir `
    -WindowStyle Hidden -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr
Set-Content -Path $PidFile -Value $proc.Id -Encoding ascii

$ready = $false
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Milliseconds 500
    if ($proc.HasExited) { break }
    if (Test-KaiHealth $port) { $ready = $true; break }
}

if (-not $ready) {
    Remove-Item $PidFile -ErrorAction SilentlyContinue
    Write-Host ""
    Write-Host "KAI Core no pudo iniciar. Últimas líneas del registro:" -ForegroundColor Red
    if (Test-Path $stderr) { Get-Content $stderr -Tail 20 }
    Fail "Revisá docs\TROUBLESHOOTING.md (puerto ocupado, dependencias, .env inválido)."
}

Write-Ok "KAI está activo (PID $($proc.Id)). Para detenerlo: scripts\stop.ps1"
if (-not $NoBrowser) { Start-Process "http://127.0.0.1:$port" }
