# Dedicated Windows release helper:
# 1) Download the latest GitHub source zip (or a tag)
# 2) Extract under D:\trainz-project\mstn-trainz-studio-build
# 3) Compile static win64 and write TrainzStudio-*-win64.zip
# 4) Optional: upload to the matching GitHub release (-Upload)
#
# Usage (from anywhere):
#   powershell -File D:\trainz-project\mstn-trainz-studio\tools\fetch_latest_and_pack_windows.ps1
#   powershell -File ...\fetch_latest_and_pack_windows.ps1 -Tag v4.4.6 -Upload
param(
    [string]$Tag = "",
    [string]$WorkRoot = "D:\trainz-project\mstn-trainz-studio-build",
    [switch]$Upload,
    [switch]$SkipChecks,
    [switch]$UseLocalRepo
)
$ErrorActionPreference = "Stop"

$repo = "naseno15/mstn-trainz-studio"
$api = "https://api.github.com/repos/$repo"

if (-not $Tag) {
    $latest = Invoke-RestMethod "$api/releases/latest"
    $Tag = $latest.tag_name
    if (-not $Tag) { throw "cannot resolve latest release tag" }
}
Write-Host "tag=$Tag"

if ($UseLocalRepo) {
    $src = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
    Write-Host "use local repo: $src"
    $packRoot = $src
} else {
    $zipUrl = "https://github.com/$repo/archive/refs/tags/$Tag.zip"
    $zipPath = Join-Path $env:TEMP "mstn-trainz-studio-$Tag.zip"
    Write-Host "download $zipUrl"
    curl.exe -L --retry 5 -o $zipPath $zipUrl
    if ($LASTEXITCODE) { throw "download source zip failed" }

    if (Test-Path $WorkRoot) { Remove-Item $WorkRoot -Recurse -Force }
    New-Item -ItemType Directory -Force $WorkRoot | Out-Null
    Expand-Archive $zipPath $WorkRoot -Force
    $packRoot = Get-ChildItem $WorkRoot -Directory | Select-Object -First 1 -ExpandProperty FullName
    if (-not $packRoot) { throw "extract failed — no folder under $WorkRoot" }
    Write-Host "extracted: $packRoot"
}

$pack = Join-Path $packRoot "fast_pack_windows.ps1"
if (-not (Test-Path $pack)) {
    # Tag zip from before this script existed: fall back to local pack script against extracted tree.
    $localPack = Join-Path (Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)) "fast_pack_windows.ps1"
    if (-not (Test-Path $localPack)) { throw "fast_pack_windows.ps1 missing" }
    Copy-Item $localPack $pack -Force
}

$args = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $pack, "-Tag", $Tag)
if ($Upload) { $args += "-Upload" }
if ($SkipChecks) { $args += "-SkipChecks" }
Write-Host "run: powershell $($args -join ' ')"
& powershell @args
if ($LASTEXITCODE) { throw "pack failed" }
