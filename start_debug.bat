@echo off
REM Debug launch — console visible (python.exe)
setlocal
set HERE=%~dp0
set VENV=%HERE%.venv
if not exist "%VENV%\Scripts\python.exe" (
  echo Creating venv + installing deps...
  python -m venv "%VENV%"
  "%VENV%\Scripts\pip.exe" install -r "%HERE%requirements.txt"
)
if not exist "%HERE%vendor\assimp\Release\assimp-vc143-mt.dll" (
  where assimp >nul 2>&1
  if errorlevel 1 (
    echo warning: Assimp DLL/CLI missing — FBX load will fail.
  )
)
cd /d "%HERE%.."
"%VENV%\Scripts\python.exe" -m trainz_studio %*
