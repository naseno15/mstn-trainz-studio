@echo off
setlocal
REM Build MSTN_TrainzStudio onedir into trainz_studio\dist\
cd /d "%~dp0.."
set PY=.venv\Scripts\python.exe
if not exist "%PY%" set PY=python

echo [build] python: %PY%
"%PY%" -m pip install -q "pyinstaller>=6.0"
if errorlevel 1 exit /b 1

"%PY%" -m PyInstaller --noconfirm --distpath dist --workpath build\pyi pack\trainz_studio.spec
if errorlevel 1 exit /b 1

echo.
echo [build] OK → %CD%\dist\MSTN_TrainzStudio\MSTN_TrainzStudio.exe
exit /b 0
