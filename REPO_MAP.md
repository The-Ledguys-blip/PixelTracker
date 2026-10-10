# PixelTracker — Repository Map

Laatst bijgewerkt: 20-08-2026
Branch: `main` (HEAD `e19ad6e`)

---

## Overzicht

PixelTracker is een desktop-app voor het registreren en beheren van pixelreparaties aan LED-modules. De app combineert een **Python/PyQt6 desktop-shell** met een **HTML/JavaScript frontend** die in een WebEngine-view draait. Er is ook een legacy **Tkinter**-versie.

---

## Projectstructuur

```
PixelTracker-repo/
├── .github/
│   └── workflows/
│       └── build-windows.yml       # CI: Windows 11 build (Inno Setup + MSI)
├── assets/
│   ├── app_icon.icns               # macOS app-icon
│   ├── app_icon.ico                # Windows app-icon
│   ├── app_icon.png                # PNG app-icon (gebruikt door de desktop-shell)
│   └── pixel_repair_app.html       # HOOFDBESTAND: volledige web-frontend (4518 regels)
├── build/
│   ├── PixelTracker.spec           # PyInstaller spec (macOS)
│   ├── PixelTracker-Windows.spec   # PyInstaller spec (Windows)
│   ├── version_info_windows.txt    # Windows versie-info (3.0.25 Beta)
│   └── PixelTracker/               # PyInstaller build-output
├── Desktop/                        # Leeg (verwijst naar originele Desktop-bron)
├── dist/                           # Build-output (installers/exe)
├── installer/
│   ├── PixelTracker-Windows.iss    # Inno Setup script (.exe installer)
│   └── PixelTracker-Windows.wxs    # WiX Toolset script (.msi installer)
├── src/
│   ├── pixel_repair_desktop.py     # PyQt6 desktop-shell (772 regels)
│   └── pixel_repair_app.py         # Legacy Tkinter-versie (1530 regels)
├── tests/
│   ├── test_export_preview_layout.py   # Tests voor HTML export-layout
│   └── test_pixel_repair_desktop.py    # Tests voor desktop-shell
├── .gitignore
├── .venv/                          # Python virtuele omgeving
├── README.md                       # Startinstructies
├── REPO_MAP.md                     # Dit bestand
├── build_msi.ps1                   # Windows MSI build-script
├── build_windows.ps1               # Windows Inno Setup build-script
├── requirements.txt                # Python dependencies
└── run_dev.sh                      # macOS dev-launcher
```

---

## Hoofdcomponenten

### 1. `src/pixel_repair_desktop.py` — Desktop-shell (PyQt6)

De **primaire desktop-app**. Draait de HTML-frontend in een `QWebEngineView`.

| Onderdeel | Beschrijving |
|---|---|
| `PixelTrackerWindow` | Hoofdvenster (QMainWindow). Beheert close-gedrag, titel, PDF-export via JS. |
| `PixelTrackerPage` | Aangepaste QWebEnginePage. Vangt `pixeltracker://export` navigatie af. |
| `PixelTrackerWebView` | Kern-webview. Beheert profiel, downloads, PDF-export, zoom, pan, print. |
| `app_data_dir()` | Platform-specifieke data-map (`~/Library/Application Support/PixelTracker` op macOS). |
| `html_file()` / `persistent_html_file()` | Zoekt/kopieert de HTML-frontend naar de app-data-map. |
| `BRIDGE_SCRIPT` | JS-bridge ingespoten in de pagina: `zoomBySteps()` en `panBy()` voor native zoom/pan. |
| PDF-export | Screencapture + ReportLab → crop-regio's → A3 landscape PDF's. |
| JSON-download | Vangt downloads af, atomische save (`os.replace`) naar huidige database-pad. |

**Belangrijkste functies:**
- `export_current_report_to_pdf()` — exporteert 1 module of hele database als PDF(s)
- `_save_module_pdf_sequentially()` — per module/segment een PDF via canvas-crops
- `_save_multi_page_pdf_from_crops()` — multi-page PDF via ReportLab
- `on_download_requested()` — JSON/CSV download met "Opslaan als"-dialoog
- `wheelEvent()` / `event()` — Ctrl/Cmd+scroll en pinch-to-zoom doorsturen naar JS

### 2. `assets/pixel_repair_app.html` — Web-frontend (4518 regels)

De **volledige applicatie-UI** in één HTML-bestand met inline CSS en JavaScript.

**UI-secties:**
- Menubalk met dropdown-menu's (Bestand, Module, Reparaties, Weergave, Updates)
- Linkerkolom: module-dataformulier (bedrijf, naam, SN, afmetingen, shader-grootte)
- Middelste kolom: pixelcanvas met linialen, grid, zoom-schuif, selectie/hand-tool
- Rechterkolom: reparatiestatus, legenda, statistieken
- Onderste tabel: alle modules uit de database
- Modals: reparatie-modal, preset-manager, quick-edit, startup-choice overlay
- Print/export-view: dual-canvas layout (Detail + Module Overview) per shader-segment

**JavaScript-modules (functies in globale scope):**
- `renderAll()` / `renderCanvas()` / `renderModuleList()` / `renderAllModulesTable()` / `renderStats()` — kern-rendering
- `buildPrintPage()` / `buildSegmentGroups()` / `buildSegmentReportPage()` / `buildSampleReportData()` — A3 export-preview
- `exportPrintA3('selected'|'database')` — print-export via module-batches
- `save()` / `load()` / `exportDatabaseJson()` / `syncLibraryFromModules()` — data-opslag
- `pushHistory()` / `undo()` / `redo()` — ongedaan-maken
- `quickAddRepair()` — snelreparaties (1/2/3 toetsen)
- `openQuickEditModal()` / `scanUpdateSn()` / `renameModule()` / `renameModuleName()` — contextmenu-bewerking
- `hideAppShellForExport()` / `restoreAppShellAfterExport()` / `forceRestoreAfterExport()` — export-weergave

**Bruggen naar desktop (globale window-variabelen):**
| Variabele | Doel |
|---|---|
| `window.__pixelTrackerDesktop` | Markeert desktop-omgeving (onderdrukt afterprint-restore) |
| `window.__pixelTrackerExportMode` | `'selected'` of `'database'` |
| `window.__pixelTrackerExportName` | PDF-bestandsnaam voor export |
| `window.__pixelTrackerExportFolderName` | Mapnaam voor database-export |
| `window.__pixelTrackerBuildSampleExport()` | Genereert voorbeeld-export |
| `window.__pixelTrackerHideAppShellForExport()` | Verbergt app-UI voor export |
| `window.__pixelTrackerForceExportRestore()` | Forceert herstel na export |
| `window.__pixelTrackerRequestClose()` | Close-gedrag: `close_clean`/`pending`/`discard_close` |
| `window.__pixelTrackerDatabaseSaveMode` | JSON-save modus: `save` of `save_as` |

### 3. `src/pixel_repair_app.py` — Legacy Tkinter-versie

Oudere zelfstandige Tkinter-app met vergelijkbare functionaliteit (zonder web-frontend).

**Datamodel (dataclasses):**
- `Repair` — id, type, datum, initialen, status, kleur, notitie, pixel-lijst
- `Module` — id, bedrijf, naam, serienummer, breedte/hoogte, reparaties
- `AppState` — actieve module-id + modules-woordenboek

**Kernfeatures:**
- Pixelcanvas met zoom, selectie, slepen, ruimte-toets voor pannen
- Module- en reparatiebeheer via Tkinter-UI
- A3 PDF-export via ReportLab
- JSON-import/export, CSV-export
- Thema (light/dark), ongedaan-maken/redo
- Toetsenbord-sneltoetsen (1/2/3 voor snelreparaties)

### 4. Build-systeem

| Bestand | Doel |
|---|---|
| `requirements.txt` | PyQt6, PyQt6-WebEngine, Pillow, PyInstaller, reportlab |
| `build/PixelTracker.spec` | macOS PyInstaller-configuratie (versie 3.0.25) |
| `build/PixelTracker-Windows.spec` | Windows PyInstaller-configuratie |
| `build/version_info_windows.txt` | Windows versie-info: 3.0.25 Beta |
| `build_windows.ps1` | Volledige Windows-build: venv → PyInstaller → Inno Setup → `.exe` |
| `build_msi.ps1` | MSI-build via WiX Toolset (`heat.exe`, suppressions ICE38/64/91) |
| `installer/PixelTracker-Windows.iss` | Inno Setup: per-user install met `PrivilegesRequired=lowest` |
| `installer/PixelTracker-Windows.wxs` | WiX MSI-definitie (UpgradeCode `4DF480CF-...`) |
| `.github/workflows/build-windows.yml` | GitHub Actions: `windows-2022`, `workflow_dispatch`, publiceert Setup.exe + MSI |

### 5. Tests (`tests/`)

| Bestand | Test-inhoud |
|---|---|
| `test_pixel_repair_desktop.py` | HTML-padvinding, macOS/Windows app-data-paden, PDF-capture-hoogtes, atomic JSON-save |
| `test_export_preview_layout.py` | HTML-contract: startup-overlay, export-layout (segmentgroups, dual-canvas, footprint), contextmenu-actions, installer-contract (spec/iss/wxs/msi/workflow), buildversie |

---

## Data & opslag

| Locatie | Doel |
|---|---|
| `~/Library/Application Support/PixelTracker/` (macOS) | HTML-kopie, web-profiel (storage/cache), cookies |
| `%LOCALAPPDATA%\PixelTracker\` (Windows) | idem |
| `~/.pixeltracker_db.json` (legacy Tkinter) | Database in home-map |
| `~/.pixeltracker_theme.json` (legacy Tkinter) | Thema-voorkeur |
| `~/Downloads` | PDF-export-uitvoer (bestanden + `_exports`-mappen) |

---

## Build-versies

| Versie | Laag | Waar |
|---|---|---|
| `3.0.25 Beta` | Windows-installer | `build_windows.ps1`, `version_info_windows.txt`, `.iss`, `.wxs` |
| `3.0.25` | macOS spec + HTML-build | `build/PixelTracker.spec`, `const BUILD_VERSION = 'V3.0.25 Beta'` in HTML |

---

## Git-status (20-08-2026)

```
e19ad6e (HEAD -> main, origin/main) Fix Windows MSI linking
2a52c7f Run Windows installer build on main
ed54804 Add Windows MSI build for V2.1.32
2484059 Add in-app updates menu and changelog window
e25c661 Initial PixelTracker editable repo setup
```

**Niet-gecommitete wijzigingen:**
- `assets/pixel_repair_app.html` (gewijzigd)
- `build/PixelTracker.spec` (gewijzigd)
- `build_msi.ps1` (gewijzigd)
- `src/pixel_repair_desktop.py` (gewijzigd)
- `tests/test_export_preview_layout.py` (gewijzigd)
- `tests/test_pixel_repair_desktop.py` (gewijzigd)
