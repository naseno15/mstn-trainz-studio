@echo off
REM Delegates to start.vbs so drag-drop / double-click never shows a console.
wscript //nologo "%~dp0start.vbs" %*
exit /b 0
