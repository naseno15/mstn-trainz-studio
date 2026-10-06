@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0register.ps1" %*
exit /b %ERRORLEVEL%
