$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if ($env:OS -ne "Windows_NT") {
    throw "Deze build moet op Windows 11 worden uitgevoerd."
}

$Python = Join-Path $PSScriptRoot ".venv-win\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    py -3.12 -m venv .venv-win
}

& $Python -m pip install --upgrade pip
& $Python -m pip install -r requirements.txt
& $Python -m PyInstaller --clean --noconfirm build\PixelTracker-Windows.spec

# ---------- Optionele code-signing ----------
# Zonder certificaat blijft de build ongewijzigd (unsigned, zoals voorheen).
# Voor distributie:
#   $env:PIXELTRACKER_WIN_CERT = "C:\pad\naar\cert.pfx"
#   $env:PIXELTRACKER_WIN_CERT_PASSWORD = "geheim"
#   (of $env:PIXELTRACKER_WIN_CERT_THUMBPRINT voor een cert in de cert-store)
$Cert = $env:PIXELTRACKER_WIN_CERT
$CertThumbprint = $env:PIXELTRACKER_WIN_CERT_THUMBPRINT
if ($Cert -or $CertThumbprint) {
    $Signtool = Get-ChildItem "${env:ProgramFiles(x86)}\Windows Kits\10\bin\*\x64\signtool.exe" -ErrorAction SilentlyContinue |
        Sort-Object FullName -Descending | Select-Object -First 1
    if (-not $Signtool) {
        throw "signtool.exe niet gevonden. Installeer de Windows SDK."
    }
    $Target = "dist\PixelTracker-Windows\PixelTracker.exe"
    if ($Cert) {
        & $Signtool.FullName sign /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 `
            /f $Cert /p $env:PIXELTRACKER_WIN_CERT_PASSWORD $Target
    } else {
        & $Signtool.FullName sign /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 `
            /sha1 $CertThumbprint $Target
    }
    Write-Host "Binair bestand ondertekend: $Target"
} else {
    Write-Host "PIXELTRACKER_WIN_CERT niet gezet: build wordt NIET ondertekend."
}

$InnoCandidates = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
)
$Iscc = $InnoCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $Iscc) {
    throw "Inno Setup 6 ontbreekt. Installeer het met: winget install JRSoftware.InnoSetup"
}

& $Iscc installer\PixelTracker-Windows.iss
Write-Host "Installer gereed: dist\PixelTracker_V3.0.33_Beta_Windows11_Setup.exe"
