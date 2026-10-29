# PixelTracker (Editable Repo)

Deze map bevat de teruggevonden broncode om de app verder te bewerken.

## Structuur
- `src/` broncode
- `assets/` iconen en HTML-assets
- `build/` packaging-bestand

## Snel starten
1. Maak een virtuele omgeving:
   - `python3 -m venv .venv`
2. Activeer de omgeving:
   - `source .venv/bin/activate`
3. Installeer dependencies:
   - `pip install -r requirements.txt`
4. Start desktop shell:
   - `python src/pixel_repair_desktop.py`

## Alternatief
Start de Tk-app direct:
- `python src/pixel_repair_app.py`

## Windows 11 installer bouwen
De Windows-installer moet op Windows 11 x64 worden gebouwd, omdat PyInstaller de Windows-versies van Python, Qt en WebEngine bundelt.

Vereisten:
- Python 3.12 x64
- Inno Setup 6 (`winget install JRSoftware.InnoSetup`)

Voer vanuit PowerShell in de repository uit:

```powershell
.\build_windows.ps1
```

Resultaat:
- `dist\PixelTracker_V3.0.33_Beta_Windows11_Setup.exe`

Voor een MSI-installer installeer je ook WiX Toolset 3 (`winget install WiXToolset.WiXToolset`) en voer je uit:

```powershell
.\build_msi.ps1
```

Resultaat:
- `dist\PixelTracker_V3.0.33_Beta_Windows11.msi`

## Code-signing en notarisatie (optioneel)

Zonder certificaten bouwt het project gewoon ongewijzigd (unsigned). Voor
distributie buiten de eigen organisatie zijn ondertekende builds nodig; beide
buildscripts schakelen dit automatisch in zodra de juiste variabelen zijn gezet.

### macOS

1. Zorg voor een **Developer ID Application**-certificaat in de sleutelhanger.
2. Sla een notarisatie-profiel op:
   - `xcrun notarytool store-credentials pixeltracker-notary --apple-id "..." --team-id "..." --password "app-specifiek-wachtwoord"`
3. Bouw met:
   - `export PIXELTRACKER_SIGN_IDENTITY="Developer ID Application: Naam (TEAMID)"`
   - `export PIXELTRACKER_NOTARY_PROFILE="pixeltracker-notary"`
   - `./build_macos.sh`

De app wordt ondertekend met hardened runtime + `build/entitlements.macos.plist`,
genotariseerd en gestapeld (zowel de `.app` als de `.dmg`).

### Windows

1. `$env:PIXELTRACKER_WIN_CERT = "C:\pad\cert.pfx"` en
   `$env:PIXELTRACKER_WIN_CERT_PASSWORD = "geheim"`
   (of `$env:PIXELTRACKER_WIN_CERT_THUMBPRINT` voor een certificaat in de store).
2. Bouw met `.\build_windows.ps1`.

Het binaire bestand wordt met `signtool` ondertekend (SHA-256 + tijdstempel).

## Logboek en back-ups

- Logboek (roterend, o.a. crashes en JS-fouten):
  `~/Library/Application Support/PixelTracker/logs/pixeltracker.log`
- Automatische back-ups van databases (laatste 10 per bestand):
  `~/Library/Application Support/PixelTracker/backups/`
- Herstellen via het menu **Bestand → Back-ups herstellen...** of bekijk de
  paden in **Help → Over PixelTracker...** (met "Kopieer systeeminfo").
