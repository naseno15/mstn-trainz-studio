# Register Trainz mesh Open / Quick Preview (per-user HKCU).
# Run:  powershell -ExecutionPolicy Bypass -File register.ps1
# Optional:  -ExePath "D:\...\MSTN_TrainzStudio.exe"
#            -Source   (use package venv python -m trainz_studio)
#            -WithExplorerPane  (opt-in COM handler — flaky on Win11; off by default)
param(
    [string]$ExePath = "",
    [switch]$Source,
    [switch]$WithExplorerPane,
    [switch]$SkipHandler  # legacy alias of default (pane off)
)
$SkipHandler = $SkipHandler -or (-not $WithExplorerPane)

$ErrorActionPreference = "Stop"
$ShellDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PackDir = Split-Path -Parent $ShellDir
$PkgRoot = Split-Path -Parent $PackDir
$RepoRoot = Split-Path -Parent $PkgRoot
$BinDir = Join-Path $ShellDir "bin"
$CsPath = Join-Path $ShellDir "MeshPreviewHandler.cs"
$DllPath = Join-Path $BinDir "MeshPreviewHandler.dll"

$Clsid = "{8F3E2A1B-6C4D-4E9F-B2A1-7D5E9C3F0A12}"
$PreviewShellex = "{8895b1c6-b41f-4c1c-a562-0d564250836f}"
$PreviewCat = "{867738B9-6CF2-4DE8-8767-F794EBE749F6}"
$AppId = $Clsid
$Exts = @(".trainzmesh", ".im", ".fbx")
$ProgId = "MSTN.TrainzMesh"

function Resolve-Launch {
    if ($Source) {
        $py = Join-Path $PkgRoot ".venv\Scripts\python.exe"
        if (-not (Test-Path $py)) { $py = "python" }
        return "`"$py`" -m trainz_studio"
    }
    if ($ExePath -and (Test-Path $ExePath)) {
        return "`"$ExePath`""
    }
    $dist = Join-Path $PkgRoot "dist\MSTN_TrainzStudio\MSTN_TrainzStudio.exe"
    if (Test-Path $dist) { return "`"$dist`"" }
    # Legacy location from when the package lived under tools/
    $legacy = Join-Path $RepoRoot "tools\dist\MSTN_TrainzStudio\MSTN_TrainzStudio.exe"
    if (Test-Path $legacy) { return "`"$legacy`"" }
    $py = Join-Path $PkgRoot ".venv\Scripts\python.exe"
    if (Test-Path $py) {
        Write-Host "[shell] no frozen exe - using venv python (-Source mode)"
        return "`"$py`" -m trainz_studio"
    }
    throw "No MSTN_TrainzStudio.exe and no .venv python. Pass -ExePath or -Source."
}

$Launch = Resolve-Launch
# -m trainz_studio needs cwd=repo\; frozen exe uses its own folder.
$PreviewCwd = if ($Launch -match '-m trainz_studio') { $RepoRoot } else {
    if ($Launch -match 'MSTN_TrainzStudio\.exe') {
        Split-Path -Parent ($Launch.Trim('"'))
    } else { $RepoRoot }
}
$OpenCmd = "$Launch `"%1`""
$PreviewCmd = "$Launch --preview `"%1`""

Write-Host "[shell] PreviewLaunch = $Launch"
Write-Host "[shell] PreviewCwd    = $PreviewCwd"

# --- compile preview handler DLL ---
if (-not $SkipHandler) {
    New-Item -ItemType Directory -Force -Path $BinDir | Out-Null
    Write-Host "[shell] compiling MeshPreviewHandler.dll ..."
    $code = Get-Content -Raw -Encoding UTF8 -Path $CsPath
    # Keep deps minimal — WinForms in the COM type breaks prevhost CoCreate on Win11.
    Add-Type -TypeDefinition $code -OutputAssembly $DllPath -OutputType Library `
        -ReferencedAssemblies @("System.dll", "System.Core.dll")
    if (-not (Test-Path $DllPath)) { throw "DLL build failed: $DllPath" }
    # Prefer DLL beside frozen exe when registering that build.
    if ($Launch -match 'MSTN_TrainzStudio\.exe') {
        $exeDir = Split-Path -Parent ($Launch.Trim('"'))
        $ship = Join-Path $exeDir "MeshPreviewHandler.dll"
        Copy-Item -Force $DllPath $ship
        $DllPath = $ship
    }
    Write-Host "[shell] OK $DllPath"
}

# --- MSTN install key ---
$mstn = "HKCU:\Software\MSTN\TrainzStudio"
New-Item -Path $mstn -Force | Out-Null
Set-ItemProperty -Path $mstn -Name "PreviewLaunch" -Value $Launch
Set-ItemProperty -Path $mstn -Name "PreviewCwd" -Value $PreviewCwd
Set-ItemProperty -Path $mstn -Name "InstallRoot" -Value $PkgRoot

# --- ProgID ---
$pidKey = "HKCU:\Software\Classes\$ProgId"
New-Item -Path $pidKey -Force | Out-Null
Set-ItemProperty -Path $pidKey -Name "(default)" -Value "Trainz Mesh"
New-Item -Path "$pidKey\DefaultIcon" -Force | Out-Null
# ponytail: frozen exe icon; source uses venv python icon (not blank shell32 doc)
$icon = if ($Launch -match 'MSTN_TrainzStudio\.exe') {
    ($Launch.Trim('"') + ",0")
} elseif ($Launch -match 'python\.exe') {
    if ($Launch -match '"([^"]+python\.exe)"') { "$($Matches[1]),0" } else { "shell32.dll,0" }
} else { "shell32.dll,0" }
Set-ItemProperty -Path "$pidKey\DefaultIcon" -Name "(default)" -Value $icon

New-Item -Path "$pidKey\shell\open\command" -Force | Out-Null
Set-ItemProperty -Path "$pidKey\shell\open\command" -Name "(default)" -Value $OpenCmd

New-Item -Path "$pidKey\shell\quickpreview" -Force | Out-Null
Set-ItemProperty -Path "$pidKey\shell\quickpreview" -Name "(default)" -Value "Quick Preview"
New-Item -Path "$pidKey\shell\quickpreview\command" -Force | Out-Null
Set-ItemProperty -Path "$pidKey\shell\quickpreview\command" -Name "(default)" -Value $PreviewCmd

# --- extensions + ProgID ShellEx (Explorer resolves either path) ---
foreach ($ext in $Exts) {
    $ek = "HKCU:\Software\Classes\$ext"
    New-Item -Path $ek -Force | Out-Null
    Set-ItemProperty -Path $ek -Name "(default)" -Value $ProgId
    New-Item -Path "$ek\OpenWithProgids" -Force | Out-Null
    New-ItemProperty -Path "$ek\OpenWithProgids" -Name $ProgId -PropertyType String -Value "" -Force | Out-Null
    if (-not $SkipHandler) {
        $sx = "$ek\ShellEx\$PreviewShellex"
        New-Item -Path $sx -Force | Out-Null
        Set-ItemProperty -Path $sx -Name "(default)" -Value $Clsid
    }
}
if (-not $SkipHandler) {
    $psx = "$pidKey\ShellEx\$PreviewShellex"
    New-Item -Path $psx -Force | Out-Null
    Set-ItemProperty -Path $psx -Name "(default)" -Value $Clsid
}

# --- COM CLSID (per-user .NET InProc + prevhost surrogate) ---
if (-not $SkipHandler) {
    $codeBase = ([Uri]$DllPath).AbsoluteUri
    $cl = "HKCU:\Software\Classes\CLSID\$Clsid"
    New-Item -Path $cl -Force | Out-Null
    Set-ItemProperty -Path $cl -Name "(default)" -Value "MSTN Trainz Mesh Preview Handler"
    Set-ItemProperty -Path $cl -Name "AppID" -Value $AppId
    # OpenGL child needs this - otherwise prevhost Low IL blocks the spawn/embed.
    New-ItemProperty -Path $cl -Name "DisableLowILProcessIsolation" -PropertyType DWord -Value 1 -Force | Out-Null

    $inproc = "$cl\InprocServer32"
    New-Item -Path $inproc -Force | Out-Null
    Set-ItemProperty -Path $inproc -Name "(default)" -Value "mscoree.dll"
    Set-ItemProperty -Path $inproc -Name "ThreadingModel" -Value "Both"
    Set-ItemProperty -Path $inproc -Name "Class" -Value "MSTN.Shell.MeshPreviewHandler"
    Set-ItemProperty -Path $inproc -Name "Assembly" -Value "MeshPreviewHandler, Version=0.0.0.0, Culture=neutral, PublicKeyToken=null"
    Set-ItemProperty -Path $inproc -Name "RuntimeVersion" -Value "v4.0.30319"
    Set-ItemProperty -Path $inproc -Name "CodeBase" -Value $codeBase

    $cat = "$cl\Implemented Categories\$PreviewCat"
    New-Item -Path $cat -Force | Out-Null

    # Managed handlers need their own prevhost instance (MSDN). Also point CLSID AppID here.
    $app = "HKCU:\Software\Classes\AppID\$AppId"
    New-Item -Path $app -Force | Out-Null
    Set-ItemProperty -Path $app -Name "DllSurrogate" -Value "prevhost.exe"
    # Approved list (some Explorer builds skip unlisted handlers).
    $approved = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Shell Extensions\Approved"
    New-Item -Path $approved -Force | Out-Null
    New-ItemProperty -Path $approved -Name $Clsid -PropertyType String `
        -Value "MSTN Trainz Mesh Preview Handler" -Force | Out-Null

    # MSDN catalog — without this Win11 often shows "No preview available" even with ShellEx.
    $ph = "HKCU:\Software\Microsoft\Windows\CurrentVersion\PreviewHandlers"
    New-Item -Path $ph -Force | Out-Null
    New-ItemProperty -Path $ph -Name $Clsid -PropertyType String `
        -Value "MSTN Trainz Mesh Preview Handler" -Force | Out-Null
}

# notify shell
try {
    $sig = @'
[DllImport("shell32.dll")] public static extern void SHChangeNotify(int wEventId, uint uFlags, IntPtr dwItem1, IntPtr dwItem2);
'@
    $n = Add-Type -MemberDefinition $sig -Name SHChange -Namespace Native -PassThru
    $n::SHChangeNotify(0x08000000, 0x0000, [IntPtr]::Zero, [IntPtr]::Zero)
} catch {}

Write-Host ""
Write-Host "[shell] Registered for: $($Exts -join ', ')"
Write-Host "  Open          -> full Trainz Studio"
Write-Host "  Quick Preview -> --preview (fast window)"
if (-not $SkipHandler) {
    Write-Host "  Explorer pane -> MeshPreviewHandler.dll"
    Write-Host "Enable Preview pane: Explorer -> View -> Preview pane (Alt+P)"
}
Write-Host "Done."
