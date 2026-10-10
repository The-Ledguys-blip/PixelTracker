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

$InnoCandidates = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
)
$Iscc = $InnoCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $Iscc) {
    throw "Inno Setup 6 ontbreekt. Installeer het met: winget install JRSoftware.InnoSetup"
}

& $Iscc installer\PixelTracker-Windows.iss
Write-Host "Installer gereed: dist\PixelTracker_V3.0.29_Beta_Windows11_Setup.exe"
