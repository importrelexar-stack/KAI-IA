@echo off
rem Actualiza KAI AI instalado desde el codigo (git pull + dependencias). No cambia configuraciones globales.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\update.ps1" %*
pause
