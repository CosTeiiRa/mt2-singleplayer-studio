@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Stop-Studio.ps1"
if errorlevel 1 pause
