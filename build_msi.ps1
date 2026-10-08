param(
    [switch]$SkipAppBuild
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if ($env:OS -ne "Windows_NT") {
    throw "Deze MSI-build moet op Windows 11 worden uitgevoerd."
}

if (-not $SkipAppBuild) {
    $Python = Join-Path $PSScriptRoot ".venv-win\Scripts\python.exe"
    if (-not (Test-Path $Python)) {
        py -3.12 -m venv .venv-win
    }
    & $Python -m pip install --upgrade pip
    & $Python -m pip install -r requirements.txt
    & $Python -m PyInstaller --clean --noconfirm build\PixelTracker-Windows.spec
}

$WixBin = @(
    "${env:ProgramFiles(x86)}\WiX Toolset v3.14\bin",
    "${env:ProgramFiles(x86)}\WiX Toolset v3.11\bin"
) | Where-Object { Test-Path (Join-Path $_ "heat.exe") } | Select-Object -First 1

if (-not $WixBin) {
    throw "WiX Toolset 3 ontbreekt. Installeer het met: winget install WiXToolset.WiXToolset"
}

$Heat = Join-Path $WixBin "heat.exe"
$Candle = Join-Path $WixBin "candle.exe"
$Light = Join-Path $WixBin "light.exe"
$Harvest = "build\PixelTracker-Harvest.wxs"
$ObjectDir = "build\msi-obj"

New-Item -ItemType Directory -Force $ObjectDir, "dist" | Out-Null
& $Heat dir "dist\PixelTracker-Windows" -nologo -dr INSTALLFOLDER -cg HarvestedFiles -ag -sfrag -srd -sreg -var var.SourceDir -out $Harvest
if ($LASTEXITCODE -ne 0) { throw "WiX Heat mislukte met exitcode $LASTEXITCODE." }
& $Candle -nologo -arch x64 "-dSourceDir=dist\PixelTracker-Windows" -out "$ObjectDir\" "installer\PixelTracker-Windows.wxs" $Harvest
if ($LASTEXITCODE -ne 0) { throw "WiX Candle mislukte met exitcode $LASTEXITCODE." }
& $Light -nologo -cultures:nl-NL -sice:ICE38 -sice:ICE64 -sice:ICE91 -out "dist\PixelTracker_V3.0.17_Beta_Windows11.msi" "$ObjectDir\PixelTracker-Windows.wixobj" "$ObjectDir\PixelTracker-Harvest.wixobj"
if ($LASTEXITCODE -ne 0) { throw "WiX Light mislukte met exitcode $LASTEXITCODE." }

Write-Host "MSI gereed: dist\PixelTracker_V3.0.17_Beta_Windows11.msi"
