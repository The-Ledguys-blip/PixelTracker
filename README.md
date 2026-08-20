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
- `dist\PixelTracker_V2.1.36_Beta_Windows11_Setup.exe`

Voor een MSI-installer installeer je ook WiX Toolset 3 (`winget install WiXToolset.WiXToolset`) en voer je uit:

```powershell
.\build_msi.ps1
```

Resultaat:
- `dist\PixelTracker_V2.1.36_Beta_Windows11.msi`
