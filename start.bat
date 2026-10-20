@echo off
rem Inicia KAI AI. La politica de ejecucion se omite solo para este proceso (no cambia la configuracion global).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start.ps1" %*
if errorlevel 1 pause
