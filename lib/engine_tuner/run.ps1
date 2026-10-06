# Windows launcher for Engine Tuner (PowerShell).
# Prefers trainz_studio venv. Usage:
#   .\run.ps1
#   .\run.ps1 --check
#   .\run.ps1 --no-check
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

$studioRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$repoRoot = (Resolve-Path (Join-Path $studioRoot '..')).Path
$studioPy = Join-Path $studioRoot '.venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $studioPy)) {
  Write-Error "Missing trainz_studio venv python: $studioPy"
  exit 1
}

Set-Location -LiteralPath $repoRoot

switch ($args[0]) {
  '--no-check' { }
  '--check' {
    & $studioPy -m trainz_studio.lib.engine_tuner.check @($args | Select-Object -Skip 1)
    exit $LASTEXITCODE
  }
  default {
    & $studioPy -m trainz_studio.lib.engine_tuner.check --fast
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
  }
}

& $studioPy -m trainz_studio.lib.engine_tuner
exit $LASTEXITCODE
