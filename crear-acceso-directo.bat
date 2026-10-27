@echo off
rem Crea el acceso directo "KAI AI" en el escritorio. La politica de ejecucion se omite solo para este proceso.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\create-shortcut.ps1" %*
if errorlevel 1 pause
