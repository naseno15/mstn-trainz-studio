# Remove per-user Trainz mesh shell registration.
param()
$ErrorActionPreference = "Continue"
$Clsid = "{8F3E2A1B-6C4D-4E9F-B2A1-7D5E9C3F0A12}"
$PreviewShellex = "{8895b1c6-b41f-4c1c-a562-0d564250836f}"
$Exts = @(".trainzmesh", ".im", ".fbx")
$ProgId = "MSTN.TrainzMesh"

foreach ($ext in $Exts) {
    Remove-Item -Path "HKCU:\Software\Classes\$ext\ShellEx\$PreviewShellex" -Recurse -Force -ErrorAction SilentlyContinue
    $ow = "HKCU:\Software\Classes\$ext\OpenWithProgids"
    if (Test-Path $ow) {
        Remove-ItemProperty -Path $ow -Name $ProgId -ErrorAction SilentlyContinue
    }
    $ek = "HKCU:\Software\Classes\$ext"
    if (Test-Path $ek) {
        $cur = (Get-ItemProperty -Path $ek -Name "(default)" -ErrorAction SilentlyContinue)."(default)"
        if ($cur -eq $ProgId) {
            Remove-ItemProperty -Path $ek -Name "(default)" -ErrorAction SilentlyContinue
        }
    }
}

Remove-Item -Path "HKCU:\Software\Classes\$ProgId" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path "HKCU:\Software\Classes\CLSID\$Clsid" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path "HKCU:\Software\Classes\AppID\$Clsid" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path "HKCU:\Software\MSTN\TrainzStudio" -Recurse -Force -ErrorAction SilentlyContinue
Remove-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\PreviewHandlers" `
    -Name $Clsid -ErrorAction SilentlyContinue
Remove-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Shell Extensions\Approved" `
    -Name $Clsid -ErrorAction SilentlyContinue

try {
    $sig = '[DllImport("shell32.dll")] public static extern void SHChangeNotify(int e, uint f, IntPtr a, IntPtr b);'
    $n = Add-Type -MemberDefinition $sig -Name SHChange2 -Namespace Native -PassThru
    $n::SHChangeNotify(0x08000000, 0, [IntPtr]::Zero, [IntPtr]::Zero)
} catch {}

Write-Host "[shell] Unregistered."
