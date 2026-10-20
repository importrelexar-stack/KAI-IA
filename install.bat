@echo off
rem Instala KAI AI. La politica de ejecucion se omite solo para este proceso (no cambia la configuracion global).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install.ps1" %*
pause
