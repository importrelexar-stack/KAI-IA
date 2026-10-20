<#
.SYNOPSIS
  Detiene KAI Core iniciado con scripts\start.ps1.
#>
. "$PSScriptRoot\_common.ps1"

if (-not (Test-Path $PidFile)) {
    $port = Get-KaiPort
    if (Test-KaiHealth $port) {
        Write-Warn "KAI responde en el puerto $port pero no hay PID registrado (¿se inició en modo desarrollo?)."
        Write-Warn "Cerrá la ventana de la terminal donde se está ejecutando o presioná Ctrl+C en ella."
    } else {
        Write-Ok "KAI no está en ejecución."
    }
    exit 0
}

$kaiPid = [int](Get-Content $PidFile | Select-Object -First 1)
$proc = Get-Process -Id $kaiPid -ErrorAction SilentlyContinue
# Sólo se detiene el proceso si es el Python del entorno de KAI (nunca otro proceso con el mismo PID).
if ($proc -and $proc.Path -and ((Resolve-Path $proc.Path).Path -eq (Resolve-Path $VenvPython).Path)) {
    # En Windows el python.exe del venv lanza el intérprete real como proceso hijo: se detiene el árbol completo.
    & taskkill.exe /PID $kaiPid /T /F | Out-Null
    Start-Sleep -Milliseconds 500
    if (Test-KaiHealth (Get-KaiPort)) { Fail "KAI Core sigue respondiendo. Cerralo desde el Administrador de tareas (python.exe)." }
    Write-Ok "KAI Core detenido (PID $kaiPid)."
} else {
    Write-Ok "El proceso registrado ya no estaba en ejecución."
}
Remove-Item $PidFile -ErrorAction SilentlyContinue
