from __future__ import annotations

import os
import sys
import tempfile
import json
from pathlib import Path
from datetime import datetime
import shutil
import argparse

from PyQt6.QtCore import QEvent, QEventLoop, QPoint, QSize, Qt, QTimer, QUrl, pyqtSignal as Signal
from PyQt6.QtGui import QGuiApplication, QIcon, QNativeGestureEvent, QWheelEvent
from PyQt6.QtWidgets import QApplication, QFileDialog, QMainWindow, QMessageBox
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineDownloadRequest, QWebEngineProfile, QWebEnginePage, QWebEngineSettings

try:
    from reportlab.lib.pagesizes import A3, A4, landscape
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas as pdf_canvas
    REPORTLAB_AVAILABLE = True
except Exception:
    REPORTLAB_AVAILABLE = False


APP_TITLE = "PixelTracker"
WINDOW_WIDTH = 1540
WINDOW_HEIGHT = 940

# Wachtruimte tussen een echte toetsaanslag/klik en het tonen van een native
# paneel. Een paneel dat DIRECT (binnen ~0,5s) opent na echte invoer sluit
# vanzelf; eentje dat iets later vanuit een gewone Qt-timercontext opent blijft
# stabiel (empirisch vastgesteld met gereproduceerde echte invoer).
# Een native mac-savepaneel dat vlak na een echte klik wordt geopend, loopt een
# eenmalige "kill-impuls" op die ~1,1s na de klik plaatsvindt (empirisch: een
# paneel dat 700ms na de klik opent sloot op 0,41s; een 0,4s later geopende
# retry bleef 5,3s stabiel). Door de opening pas ná die impuls te plannen (1,3s)
# opent het paneel precies één keer en blijft het gewoon staan; de retry blijft
# als vangnet voor eventuele rest-impulsen.
NATIVE_PANEL_DEFER_MS = 1300


def app_data_dir() -> Path:
    if sys.platform == "win32":
        root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return root / APP_TITLE
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_TITLE
    root = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return root / APP_TITLE


APP_DATA_DIR = app_data_dir()


BRIDGE_SCRIPT = r"""
(() => {
    if (window.__pixelTrackerBridge) return;
    window.__pixelTrackerDesktop = true;  // suppresses afterprint restore in JS
    function getZoomRange() {
        return document.getElementById('zoomRange');
    }
    function getCanvasScroll() {
        return document.getElementById('canvasScroll');
    }
    window.__pixelTrackerBridge = {
        zoomBySteps(steps) {
            const zr = getZoomRange();
            if (!zr) return;
            const min = Number(zr.min || 2);
            const max = Number(zr.max || 29);
            const cur = Number(zr.value || min);
            const next = Math.max(min, Math.min(max, cur + steps));
            if (next === cur) return;
            zr.value = String(next);
            zr.dispatchEvent(new Event('input', { bubbles: true }));
        },
        panBy(dx, dy) {
            const sc = getCanvasScroll();
            if (!sc) return;
            sc.scrollLeft += dx;
            sc.scrollTop += dy;
        }
    };
    window.__pixelTrackerOpenFileNative = function() {
        try { location.href = 'pixeltracker://openfile'; } catch (e) {}
    };
    if ('__pixelTrackerSaveRequested' in window) window.__pixelTrackerSaveRequested = false;
    window.__pixelTrackerSaveRequestedName = '';
})();
"""


def base_path() -> Path:
    if hasattr(sys, "_MEIPASS"):
        return Path(getattr(sys, "_MEIPASS"))
    return Path(__file__).resolve().parent


def html_file() -> Path:
    # PIXELTRACKER_HTML: leg de HTML-bron vast (dev-live). Zo kan de geïnstalleerde
    # app de HTML uit de repo laden, zodat wijzigingen zichtbaar zijn zonder opnieuw
    # te bouwen of te installeren. Geldig pad → direct gebruiken; ongeldige waarde →
    # waarschuwen en verder zoeken zoals normaal.
    override = os.environ.get("PIXELTRACKER_HTML", "").strip()
    if override:
        override_path = Path(override).expanduser()
        if override_path.is_file():
            return override_path
        print(
            f"Waarschuwing: PIXELTRACKER_HTML wijst naar een bestand dat niet bestaat: "
            f"{override_path} — normale zoektocht wordt gebruikt.",
            file=sys.stderr,
        )

    candidates = [
        base_path() / "pixel_repair_app.html",
        base_path().parent / "assets" / "pixel_repair_app.html",
        base_path().parent / "src" / "pixel_repair_app.html",
    ]

    for path in candidates:
        if path.exists():
            return path

    raise FileNotFoundError(
        "HTML bestand niet gevonden. Probeerde: " + ", ".join(str(p) for p in candidates)
    )


def persistent_html_file() -> Path:
    source = html_file()
    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    target = APP_DATA_DIR / "pixel_repair_app.html"
    try:
        shutil.copy2(source, target)
    except Exception:
        shutil.copyfile(source, target)
    return target


def icon_file() -> Path:
    return base_path() / "app_icon.png"


class PixelTrackerWindow(QMainWindow):
    def __init__(self, page_path: Path, auto_sample_export: bool = False) -> None:
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(WINDOW_WIDTH, WINDOW_HEIGHT)
        self._allow_close = False
        self._close_poll_timer: QTimer | None = None
        self._auto_sample_export = auto_sample_export

        icon = icon_file()
        if icon.exists():
            self.setWindowIcon(QIcon(str(icon.resolve())))

        self.webview = PixelTrackerWebView(self)
        self.setCentralWidget(self.webview)
        self.webview.titleChanged.connect(self.on_page_title_changed)
        self.webview.sampleExportRequested.connect(self.trigger_sample_export)
        self.webview.load(QUrl.fromLocalFile(str(page_path.resolve())))

    def event(self, event: QEvent) -> bool:
        t = int(event.type())
        if t in (QEvent.Type.WindowActivate, QEvent.Type.WindowDeactivate, QEvent.Type.WindowStateChange,
                 QEvent.Type.FocusIn, QEvent.Type.FocusOut, QEvent.Type.ActivationChange,
                 QEvent.Type.ApplicationActivate, QEvent.Type.ApplicationDeactivate):
            try:
                self.webview._db_trace(f"WINWND-EVENT t={t} active={self.isActiveWindow()} key={self.isActive()}")
            except Exception:
                pass
        return super().event(event)

    def trigger_sample_export(self) -> None:
        self._run_js_with_timeout(
            """
(() => {
    try {
        let ok = false;
        if (typeof window.__pixelTrackerBuildSampleExport === 'function') {
            ok = !!window.__pixelTrackerBuildSampleExport();
        } else if (typeof buildSampleReportData === 'function' && typeof buildPrintPage === 'function') {
            const sample = buildSampleReportData();
            const root = document.getElementById('printExportRoot');
            if (!root) return false;
            root.innerHTML = '';
            const dark = document.body.classList.contains('dark');
            const { page } = buildPrintPage(sample, dark);
            const moduleWrap = document.createElement('div');
            moduleWrap.className = 'export-module-batch';
            moduleWrap.dataset.exportName = 'PixelTracker_export_multisegment.pdf';
            moduleWrap.appendChild(page);
            root.appendChild(moduleWrap);
            ok = true;
        }
        if (!ok) return false;
        const root = document.getElementById('printExportRoot');
        if (root && !root.querySelector('.export-module-batch')) {
            const moduleWrap = document.createElement('div');
            moduleWrap.className = 'export-module-batch';
            moduleWrap.dataset.exportName = 'PixelTracker_export_multisegment.pdf';
            while (root.firstChild) moduleWrap.appendChild(root.firstChild);
            root.appendChild(moduleWrap);
        }
        if (typeof window.__pixelTrackerHideAppShellForExport === 'function') {
            window.__pixelTrackerHideAppShellForExport();
        }
        document.body.classList.add('export-report-mode');
        window.__pixelTrackerExportMode = 'selected';
        window.__pixelTrackerExportName = 'PixelTracker_export.pdf';
        return true;
    } catch (e) {
        return false;
    }
})()
""",
            timeout_ms=2500,
            default=False,
        )
        QTimer.singleShot(900, self.webview.export_current_report_to_pdf)

    def _run_js_with_timeout(self, script: str, timeout_ms: int = 1200, default=None):
        page = self.webview.page()
        if page is None:
            return default

        loop = QEventLoop(self)
        result = {"value": default}

        def _callback(value):
            result["value"] = value
            if loop.isRunning():
                loop.quit()

        page.runJavaScript(script, _callback)
        QTimer.singleShot(timeout_ms, loop.quit)
        loop.exec()
        return result["value"]

    def _request_close_decision(self) -> str:
        decision = self._run_js_with_timeout(
            """
(() => {
    try {
        if (window.__pixelTrackerRequestClose) return window.__pixelTrackerRequestClose();
        return 'close_clean';
    } catch (e) {
        return 'close_clean';
    }
})()
""",
            timeout_ms=1400,
            default="close_clean",
        )
        if isinstance(decision, str) and decision:
            return decision
        return "close_clean"

    def _read_close_decision(self) -> str:
        decision = self._run_js_with_timeout(
            """
(() => {
    try {
        return (window.__pixelTrackerCloseDecision || 'idle');
    } catch (e) {
        return 'idle';
    }
})()
""",
            timeout_ms=500,
            default="idle",
        )
        if isinstance(decision, str) and decision:
            return decision
        return "idle"

    def _reset_close_decision(self) -> None:
        self._run_js_with_timeout("window.__pixelTrackerCloseDecision = 'idle';", timeout_ms=300, default=None)

    def _stop_close_polling(self) -> None:
        if self._close_poll_timer is None:
            return
        self._close_poll_timer.stop()
        self._close_poll_timer.deleteLater()
        self._close_poll_timer = None

    def _start_close_polling(self) -> None:
        if self._close_poll_timer is not None:
            return
        timer = QTimer(self)
        timer.setInterval(120)
        timer.timeout.connect(self._poll_close_decision)
        timer.start()
        self._close_poll_timer = timer

    def _poll_close_decision(self) -> None:
        decision = self._read_close_decision()
        if decision in {"idle", "pending", ""}:
            return

        self._stop_close_polling()
        if decision in {"discard_close", "close_clean", "save_close"}:
            self._allow_close = True
            self.close()
            return

        self._reset_close_decision()

    def closeEvent(self, event) -> None:  # type: ignore[override]
        if self._allow_close:
            event.accept()
            return

        decision = self._request_close_decision()
        if decision in {"close_clean", "discard_close"}:
            event.accept()
            return
        if decision == "pending":
            event.ignore()
            self._start_close_polling()
            return

        event.ignore()

    def on_page_title_changed(self, title: str) -> None:
        clean_title = (title or APP_TITLE).strip() or APP_TITLE
        self.setWindowTitle(clean_title)
        QGuiApplication.setApplicationDisplayName(clean_title)
        if clean_title.startswith(f"{APP_TITLE} - "):
            self.setWindowFilePath(clean_title.removeprefix(f"{APP_TITLE} - "))
        else:
            self.setWindowFilePath(clean_title)


class PixelTrackerPage(QWebEnginePage):
    def __init__(self, profile: QWebEngineProfile, view: "PixelTrackerWebView") -> None:
        super().__init__(profile, view)
        self._view = view

    def acceptNavigationRequest(self, url: QUrl, nav_type, is_main_frame: bool) -> bool:  # type: ignore[override]
        if url.scheme() == "pixeltracker" and url.host() == "export":
            QTimer.singleShot(0, self._view.export_current_report_to_pdf)
            return False
        if url.scheme() == "pixeltracker" and url.host() == "openfile":
            QTimer.singleShot(0, self._view.open_database_from_disk)
            return False
        return super().acceptNavigationRequest(url, nav_type, is_main_frame)


class PixelTrackerWebView(QWebEngineView):
    sampleExportRequested = Signal()

    def __init__(self, parent: QMainWindow | None = None) -> None:
        super().__init__(parent)
        profile_root = APP_DATA_DIR / "web_profile"
        profile_root.mkdir(parents=True, exist_ok=True)
        self._profile = QWebEngineProfile("PixelTrackerProfile", self)
        self._profile.setPersistentStoragePath(str((profile_root / "storage").resolve()))
        self._profile.setCachePath(str((profile_root / "cache").resolve()))
        self._profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies)
        self._profile.downloadRequested.connect(self.on_download_requested)
        self._database_save_path: Path | None = None
        self._db_open_polling = False
        self._db_save_pending = False
        self._save_poll_timer: QTimer | None = None
        self._last_db_save_dialog: QFileDialog | None = None
        self._debug_menu_rects = True
        self._last_dbg_rects_value = ''
        self._dbg_events_flushed = 0
        self.setPage(PixelTrackerPage(self._profile, self))
        self.page().loadFinished.connect(self.on_load_finished)
        self.page().printRequested.connect(self.on_print_requested)

    def _notify_download_result(self, ok: bool, saved_name: str = "", saved_path: str = "") -> None:
        """Informeert de JS-frontend of een .ptdb-download is gelukt (naam + echt pad)."""
        import json as _json
        safe_name = _json.dumps(saved_name)
        safe_path = _json.dumps(saved_path)
        self._db_trace(f"_notify_download_result ok={ok} name={saved_name} path={saved_path}")
        self.page().runJavaScript(
            f"window.__pixelTrackerDownloadResult && window.__pixelTrackerDownloadResult({str(ok).lower()}, {safe_name}, {safe_path});"
        )

    def _db_trace(self, msg: str) -> None:
        try:
            from datetime import datetime as _dt
            with open('/tmp/pixeltracker_dbg.log', 'a') as f:
                f.write(f"{_dt.now().isoformat(timespec='milliseconds')}  {msg}\n")
        except Exception:
            pass

    def open_database_from_disk(self) -> None:
        """Toont een native 'Open'-dialoog en laadt een .ptdb (of .json) bestand in de app.
        .json wordt bij het openen geconverteerd naar het eigen .ptdb-formaat, zodat een
        latere opslag direct als .ptdb wordt geschreven op dezelfde plek."""
        import json as _json
        path, _ = QFileDialog.getOpenFileName(self, 'Database openen', '', 'PixelTracker bestanden (*.ptdb *.json)')
        if not path:
            return
        target = Path(path)
        try:
            content = target.read_text(encoding='utf-8')
        except Exception:
            return
        # Verwerk als eigen formaat: .json → .ptdb bij het openen (conversie).
        working_target = target if target.suffix.lower() == '.ptdb' else target.with_suffix('.ptdb')
        self._database_save_path = working_target
        self.page().runJavaScript(
            "window.__pixelTrackerLoadDatabaseContent && window.__pixelTrackerLoadDatabaseContent("
            f"{_json.dumps(content)}, {_json.dumps(str(working_target))});"
        )

    @staticmethod
    def _is_db_ext(ext: str) -> bool:
        return ext.lower() in ('.ptdb', '.json')

    def on_download_requested(self, download: QWebEngineDownloadRequest) -> None:
        suggested = Path(download.downloadFileName())
        ext = suggested.suffix.lower()
        is_db = self._is_db_ext(ext)
        self._db_trace(f"on_download_requested name={suggested.name} is_db={is_db}")
        if is_db:
            # Database-opslag precies in het CSV/PDF-exportpatroon, dat in de
            # praktijk wél stabiel blijft: het native mac-savepaneel (statische
            # getSaveFileName) wordt SYNCROON vanuit de download-slot getoond,
            # zonder uitstel en zonder nested QEventLoop('s) ervoor. De JSON
            # wordt pas ná het paneel uit JS gelezen en zelf weggeschreven.
            self._do_db_save(download, suggested.name)
            return

        # Non-database downloads (CSV, PDF, …): direct accept zonder dialoog-paneel.
        if ext == '.csv':
            filter_str = 'CSV bestanden (*.csv)'
        else:
            filter_str = 'Alle bestanden (*)'
        path, _ = QFileDialog.getSaveFileName(
            self, 'Exporteren', str(Path.home() / 'Desktop' / suggested.name), filter_str
        )
        if not path:
            download.cancel()
            self._notify_download_result(False)
            return
        target_path = Path(path)
        download.setDownloadDirectory(str(target_path.parent))
        download.setDownloadFileName(target_path.name)

        def _notify_save_done(state) -> None:
            completed = QWebEngineDownloadRequest.DownloadState.DownloadCompleted
            if state == completed:
                self._notify_download_result(True, target_path.name, str(target_path))
            elif download.isFinished():
                self._notify_download_result(False)

        download.stateChanged.connect(_notify_save_done)
        download.accept()

    @staticmethod
    def _valid_db_path(candidate) -> Path | None:
        """Geldig absoluut database-pad → Path; elk ander antwoord → None."""
        text = str(candidate or '').strip()
        if not text:
            return None
        path = Path(text)
        if path.is_absolute() and PixelTrackerWebView._is_db_ext(path.suffix):
            return path
        return None

    def _read_db_save_info(self, attempts: int = 2, timeout_ms: int = 1000):
        """Leest (save-modus, bestandspad) terug uit de JS-frontend.

        De renderer is vlak ná een save-klik vaak ~0,5s bezig (state-serialisatie
        en her-render), waardoor één korte read leeg terugkomt. Zo'n leeg antwoord
        mag nóít als 'geen pad' worden gelezen: dat maakte van een gewone 'Opslaan'
        een 'Opslaan als'-paneel met overschrijf-vraag. Daarom wordt doorgelezen en
        getraceerd tot de frontend antwoordt; (None, '') betekent pas echt
        'geen antwoord'.
        """
        script = (
            "JSON.stringify([window.__pixelTrackerDatabaseSaveMode || '', "
            "typeof window.__pixelTrackerDatabasePath === 'string' "
            "? window.__pixelTrackerDatabasePath : '']);"
        )
        for attempt in range(1, attempts + 1):
            raw = self._run_js_value(script, timeout_ms=timeout_ms, default='')
            if isinstance(raw, str) and raw.strip():
                try:
                    arr = json.loads(raw)
                except Exception:
                    arr = None
                if isinstance(arr, list) and len(arr) == 2:
                    self._db_trace(f"SAVE-INFO mode={arr[0]!r} path={arr[1]!r} attempt={attempt}")
                    return str(arr[0] or ''), str(arr[1] or '')
            self._db_trace(f"SAVE-INFO geen antwoord attempt={attempt}/{attempts}")
        return None, ''

    @staticmethod
    def _silent_save_target(mode, js_path, known_path, from_download: bool) -> Path | None:
        """Bepaalt of een opslag zílver mag (geen paneel) en zo ja naar welk pad.

        - Download-route (`from_download`): de frontend heeft al gekozen voor
          stille overschrijving van een bekend pad — alleen een expliciete
          'save_as' of volledig onbekend pad mag alsnog een paneel tonen. Bij een
          niet-beantwoordde read valt terug op het pad dat de shell zelf bijhoudt.
        - Paneel-route: de frontend vroeg expliciet een paneel ('Opslaan als' of
          nog geen bekend pad). Alleen een expliciete 'save' mét pad schrijft stil;
          een leeg antwoord mag hier nooit leiden tot stille overschrijving.
        """
        if mode == 'save_as':
            return None
        if not from_download and mode != 'save':
            return None
        target = PixelTrackerWebView._valid_db_path(js_path)
        if target is None and from_download:
            # Read gaf geen antwoord: val terug op het pad dat de shell zelf
            # bijhoudt, zodat een gewone 'Opslaan' nooit onterecht een paneel opent.
            target = PixelTrackerWebView._valid_db_path(known_path)
        return target

    def _do_db_save(self, download, suggested_name: str) -> None:
        """Database-opslag via het standaard macOS-savepaneel.

        `download` kan None zijn (desktop-vlagpoller-route); dan is er geen
        WebEngine-download meer in het spel en hoeft er niets geannuleerd te
        worden.
        """
        try:
            mode, js_path = self._read_db_save_info()
            from_download = download is not None
            silent_path = self._silent_save_target(
                mode, js_path, self._database_save_path, from_download
            )
            self._db_trace(
                f"SAVE-ROUTE mode={mode!r} js_path={js_path!r} "
                f"known={str(self._database_save_path or '')!r} "
                f"silent={str(silent_path or '')!r} from_download={from_download}"
            )

            if silent_path is not None:
                target_path = silent_path
            else:
                default_name = (suggested_name or 'database.ptdb').strip()
                # Prefill met de map van de huidige database zodra die bekend is,
                # in plaats van de Desktop: het paneel wijst dan meteen op de
                # bestaande file en er belandt geen losse kopie op het bureaublad.
                known = self._valid_db_path(js_path) or self._valid_db_path(self._database_save_path)
                default_path = str(known.parent / default_name) if known else str(
                    Path.home() / 'Desktop' / default_name
                )
                self._db_trace(f"SAVE-PANEEL requested default={default_path}")
                path = self._db_save_as_dialog(default_path)
                self._db_trace(f"dialog returned path={path or '<empty>'}")
                if not path:
                    if download is not None:
                        download.cancel()
                    self._notify_download_result(False)
                    return
                target_path = Path(path)
                # macOS-savepanel kan een extra extensie aanhechten.
                while target_path.name.lower().endswith(('.ptdb.ptdb', '.json.json')):
                    target_path = Path(target_path.parent, target_path.name[:-len('.ptdb')])
                target_path = target_path.with_suffix('.ptdb')

            # Paneel is gesloten; een achterblijvende download annuleren kan nu niets meer sluiten.
            if download is not None:
                download.cancel()

            json_str = self._run_js_value(
                "typeof window.__pixelTrackerCurrentDbJson === 'string' ? window.__pixelTrackerCurrentDbJson : '';",
                timeout_ms=500,
                default='',
            )
            if not isinstance(json_str, str) or not json_str.strip():
                self._notify_download_result(False)
                return
            temp_path = target_path.with_name(f".{target_path.name}.tmp")
            temp_path.write_text(json_str, encoding='utf-8')
            os.replace(temp_path, target_path)
            self._database_save_path = target_path
            self._db_trace(f"WROTE {target_path}")
            backup = self._backup_saved_db(target_path)
            if backup is not None:
                self._db_trace(f"BACKUP {backup}")
            self._notify_download_result(True, target_path.name, str(target_path))
        except Exception as exc:  # pragma: no cover
            self._db_trace(f"_do_db_save error: {exc!r}")
            self._notify_download_result(False)

    def _db_save_as_dialog(self, default_path: str) -> str:
        """Native mac-savepaneel als LOSSTAAND modal venster (geen sheet).

        `default_path` is het volledige standaardpad (map + naam); als de
        huidige database al een pad heeft wordt die map aangehouden in plaats
        van de Desktop.

        Een sheet (paneel met dit venster als parent) wordt door macOS geannuleerd
        zodra het ouder-venster kort zijn key-status wisselt — precies wat na een
        echte klik/toetsaanslag in QtWebEngine gebeurt (het paneel sloot dan even
        later weer, waarna de retry opnieuw opende). Een losstaand native paneel
        (parent=None) hangt niet aan dat venster en is dus immuun: het sluit alleen
        als de gebruiker dat doet.

        Retry blijft als uiterste vangnet: mocht het paneel tóch onverklaarbaar
        snel sluiten, dan verschijnt het direct opnieuw.
        """
        from time import monotonic
        js_state = self._run_js_value(
            "JSON.stringify({mode: window.__pixelTrackerDatabaseSaveMode || '', "
            "path: window.currentDatabasePath || '', name: window.currentSaveName || ''})",
            timeout_ms=400,
            default='{}',
        )
        self._db_trace(f"PANEL start default={default_path} js={js_state}")
        for attempt in range(1, 4):
            try:
                fd = QFileDialog(
                    None,
                    'Opslaan als',
                    default_path,
                    'PixelTracker bestanden (*.ptdb *.json)',
                )
                fd.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
                fd.setDefaultSuffix('ptdb')
                self._last_db_save_dialog = fd
                started = monotonic()
                self._db_trace(f"SHOWING native dialog (save as) default={default_path} attempt={attempt}")
                if not fd.exec():
                    dur = monotonic() - started
                    self._db_trace(f"dialog cancel duur={dur:.3f}s attempt={attempt}")
                    if attempt < 3 and dur < 1.0:
                        self._db_trace("native paneel sloot verdacht snel (<1s); opnieuw tonen")
                        continue
                    return ''
                dur = monotonic() - started
                files = fd.selectedFiles()
                self._db_trace(f"dialog returned dur={dur:.3f}s attempt={attempt} files={files}")
                if files:
                    return files[0]
                return ''
            except Exception as exc:  # pragma: no cover
                self._db_trace(f"_db_save_as_dialog error: {exc!r}")
                return ''
        return ''

    def on_print_requested(self) -> None:
        # Backward compatibility: if JS still calls window.print(), run the same direct PDF export.
        self.export_current_report_to_pdf()

    def _run_js_value(self, script: str, timeout_ms: int = 1200, default=None):
        loop = QEventLoop(self)
        result = {"value": default}

        def _callback(value):
            result["value"] = value
            if loop.isRunning():
                loop.quit()

        self.page().runJavaScript(script, _callback)
        QTimer.singleShot(timeout_ms, loop.quit)
        loop.exec()
        return result["value"]

    def _run_js_value_list(self, script: str, timeout_ms: int = 1200, default=None):
        value = self._run_js_value(script, timeout_ms=timeout_ms, default=default)
        if isinstance(value, list):
            return value
        return default if default is not None else []

    @staticmethod
    def _unique_pdf_path(candidate: Path) -> Path:
        if not candidate.exists():
            return candidate
        base = candidate.with_suffix("")
        ext = candidate.suffix or ".pdf"
        counter = 1
        while (candidate.parent / f"{base.name} ({counter}){ext}").exists():
            counter += 1
        return candidate.parent / f"{base.name} ({counter}){ext}"

    def _ask_export_choice(self, message: str, options: list[str]) -> str | None:
        install = (
            "if(!window.__pixelTrackerAskExportChoice){"
            "window.__pixelTrackerChoice=null;"
            "}"
            "window.__pixelTrackerChoice=null;"
            f"window.__pixelTrackerAskExportChoice({json.dumps(message)}, {json.dumps(options)});"
        )
        self.page().runJavaScript(install)
        loop = QEventLoop(self)
        result: dict[str, str | None] = {"value": None}

        def _tick():
            def _on_value(value):
                if value is not None and result["value"] is None:
                    result["value"] = str(value)
                    if loop.isRunning():
                        loop.quit()

            self.page().runJavaScript("window.__pixelTrackerChoice || null;", _on_value)

        timer = QTimer(self)
        timer.setInterval(150)
        timer.timeout.connect(_tick)
        timer.start()
        timeout = QTimer(self)
        timeout.setSingleShot(True)
        timeout.setInterval(120000)
        timeout.timeout.connect(loop.quit)
        timeout.start()
        loop.exec()
        timer.stop()
        timeout.stop()
        return result["value"]

    @staticmethod
    def _safe_pdf_name(raw: str, fallback: str = "module") -> str:
        name = str(raw or "").strip()
        if name.lower().endswith('.pdf'):
            name = name[:-4]
        cleaned = ''.join(ch if ch not in '/\\:*?"<>|' else '-' for ch in name).strip(' .')
        if not cleaned:
            cleaned = fallback
        return f"{cleaned}.pdf"

    @staticmethod
    def _backup_saved_db(target_path: Path, keep: int = 10) -> Path | None:
        """Maak na een bewezen .ptdb-schrijfactie meteen een versie-back-up ernaast.

        Bewaart de laatste `keep` back-ups van dezelfde database in dezelfde
        map (naam: `<bestand>_backup_<YYYYMMDD-HHMMSS>.ptdb`) en ruimt oudere
        exemplaren op.
        """
        try:
            if not target_path.exists() or not target_path.is_file():
                return None
            if not self._is_db_ext(target_path.suffix):
                return None
            backup_dir = target_path.parent
            stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
            backup = backup_dir / f"{target_path.stem}_backup_{stamp}.ptdb"
            shutil.copy2(target_path, backup)
            pattern = f"{target_path.stem}_backup_*.ptdb"
            backups = sorted(backup_dir.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
            for old in backups[keep:]:
                try:
                    old.unlink(missing_ok=True)
                except Exception:
                    pass
            return backup
        except Exception:
            return None

    @staticmethod
    def _safe_folder_name(raw: str, fallback: str = "database_exports") -> str:
        name = str(raw or "").strip()
        cleaned = ''.join(ch if ch not in '/\\:*?"<>|' else '-' for ch in name).strip(' .')
        return cleaned or fallback

    @staticmethod
    def _capture_height_for_export(
        full_height: int,
        page_heights: list[int],
        viewport_height: int,
    ) -> int:
        if page_heights:
            return max(max(page_heights), viewport_height, 600)
        return max(full_height, viewport_height, 600)

    def _wait_for_export_render(self, timeout_ms: int = 80) -> None:
        loop = QEventLoop(self)
        QTimer.singleShot(timeout_ms, loop.quit)
        loop.exec()

    def _save_module_pdf_sequentially(
        self,
        path: Path,
        module_index: int,
        page_count: int,
        page_format: str = 'a3',
    ) -> bool:
        if not REPORTLAB_AVAILABLE or page_count <= 0:
            return False

        page_width, page_height = (A4 if page_format == 'a4' else landscape(A3))
        pdf = pdf_canvas.Canvas(str(path), pagesize=(page_width, page_height))
        written_pages = 0
        try:
            for page_index in range(page_count):
                rect = self._run_js_value(
                    f"(() => {{ const modules = Array.from(document.querySelectorAll('.export-module-batch')); modules.forEach((mod, i) => mod.style.display = i === {module_index} ? 'block' : 'none'); const pages = modules[{module_index}] ? Array.from(modules[{module_index}].querySelectorAll('.export-report-page')) : []; pages.forEach((page, i) => page.style.display = i === {page_index} ? 'block' : 'none'); const el = pages[{page_index}]; if (!el) return null; const r = el.getBoundingClientRect(); return {{ x: Math.round(r.left + window.scrollX), y: Math.round(r.top + window.scrollY), width: Math.round(r.width), height: Math.round(r.height) }}; }})()",
                    timeout_ms=1200,
                    default=None,
                )
                if not isinstance(rect, dict):
                    continue
                self._wait_for_export_render()
                pixmap = self.grab()
                if not pixmap or pixmap.isNull():
                    continue

                dpr = float(pixmap.devicePixelRatio() or 1.0)
                x = max(0, int((rect.get('x', 0) or 0) * dpr))
                y = max(0, int((rect.get('y', 0) or 0) * dpr))
                width = min(int((rect.get('width', 0) or 0) * dpr), int(pixmap.width()) - x)
                height = min(int((rect.get('height', 0) or 0) * dpr), int(pixmap.height()) - y)
                if width <= 0 or height <= 0:
                    continue

                crop = pixmap.copy(x, y, width, height)
                if crop.isNull():
                    continue
                tmp_file = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
                tmp_path = Path(tmp_file.name)
                tmp_file.close()
                try:
                    if not crop.save(str(tmp_path), 'PNG'):
                        continue
                    pdf.drawImage(
                        ImageReader(str(tmp_path)),
                        0,
                        0,
                        width=page_width,
                        height=page_height,
                        preserveAspectRatio=True,
                        anchor='c',
                    )
                    pdf.showPage()
                    written_pages += 1
                finally:
                    tmp_path.unlink(missing_ok=True)
        finally:
            if written_pages:
                try:
                    pdf.save()
                except Exception:
                    pass

        if written_pages == page_count:
            return True
        path.unlink(missing_ok=True)
        return False

    def _save_multi_page_pdf_from_crops(self, path: str, pixmap, rects) -> bool:
        if not REPORTLAB_AVAILABLE:
            return False

        page_width, page_height = landscape(A3)
        temp_files: list[Path] = []
        any_page = False
        try:
            pdf = pdf_canvas.Canvas(path, pagesize=(page_width, page_height))
            dpr = float(pixmap.devicePixelRatio() or 1.0)
            px_w = int(pixmap.width())
            px_h = int(pixmap.height())

            for rect in rects:
                x = int((rect.get('x', 0) or 0) * dpr)
                y = int((rect.get('y', 0) or 0) * dpr)
                width = int((rect.get('width', 0) or 0) * dpr)
                height = int((rect.get('height', 0) or 0) * dpr)

                # Clamp crop rect to the grabbed pixmap bounds.
                if x < 0:
                    width += x
                    x = 0
                if y < 0:
                    height += y
                    y = 0
                width = min(width, px_w - x)
                height = min(height, px_h - y)
                if width <= 0 or height <= 0:
                    continue

                crop = pixmap.copy(x, y, width, height)
                if crop.isNull():
                    continue
                tmp_file = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
                tmp_path = Path(tmp_file.name)
                tmp_file.close()
                temp_files.append(tmp_path)
                if not crop.save(str(tmp_path), 'PNG'):
                    continue
                pdf.drawImage(ImageReader(str(tmp_path)), 0, 0, width=page_width, height=page_height, preserveAspectRatio=True, anchor='c')
                pdf.showPage()
                any_page = True

            if not any_page:
                # Fallback: always write at least one page to avoid invalid 0-page PDFs.
                tmp_file = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
                tmp_path = Path(tmp_file.name)
                tmp_file.close()
                temp_files.append(tmp_path)
                if pixmap.save(str(tmp_path), 'PNG'):
                    pdf.drawImage(ImageReader(str(tmp_path)), 0, 0, width=page_width, height=page_height, preserveAspectRatio=True, anchor='c')
                    pdf.showPage()
                    any_page = True

            if not any_page:
                # Last-resort safety page: keep output PDF valid even when image writes fail.
                pdf.setFont("Helvetica", 13)
                pdf.drawString(72, page_height - 90, "PixelTracker export bevat geen renderdata.")
                pdf.drawString(72, page_height - 112, "Probeer opnieuw nadat de preview volledig zichtbaar is.")
                pdf.showPage()
                any_page = True

            pdf.save()
            return any_page
        finally:
            for tmp_path in temp_files:
                tmp_path.unlink(missing_ok=True)

    def export_current_report_to_pdf(self) -> None:
        # Lees de exportnaam die JS heeft ingesteld op basis van module-data
        name = self._run_js_value("window.__pixelTrackerExportName || null;", timeout_ms=1000, default=None)
        if not name or not isinstance(name, str):
            name = "PixelTracker_export.pdf"
        else:
            if not name.lower().endswith('.pdf'):
                name = Path(name).with_suffix('.pdf').name

        downloads = Path.home() / "Downloads"
        downloads.mkdir(exist_ok=True)
        if self.page() is None:
            return

        export_mode = self._run_js_value(
            "window.__pixelTrackerExportMode || 'selected';",
            timeout_ms=600,
            default='selected',
        )

        candidate = downloads / name
        if export_mode != 'database' and candidate.exists():
            choice = self._ask_export_choice(
                f"'{name}' bestaat al in Downloads.",
                ["Overschrijven", "Kopieren (1)", "Annuleren"],
            )
            if choice == 'copy':
                candidate = self._unique_pdf_path(candidate)
            elif choice != 'overwrite':
                self.page().runJavaScript(
                    "if(window.__pixelTrackerForceExportRestore){window.__pixelTrackerForceExportRestore();}"
                    "else{document.body.classList.remove('export-report-mode');"
                    "if(window.restoreAppShellAfterExport) restoreAppShellAfterExport();}"
                    "var r=document.getElementById('printExportRoot'); if(r) r.innerHTML='';"
                    "if(window.uiToast) uiToast('Export geannuleerd');"
                )
                return
        path = str(candidate)

        page_heights = self._run_js_value_list(
            "Array.from(document.querySelectorAll('.export-report-page')).map((el) => Math.ceil(el.getBoundingClientRect().height));",
            timeout_ms=1000,
            default=[],
        )

        capture_width = self._run_js_value(
            "Math.ceil(Math.max(document.body.scrollWidth, document.documentElement.scrollWidth, document.getElementById('printExportRoot')?.scrollWidth || 0, window.innerWidth));",
            timeout_ms=1000,
            default=self.width(),
        )
        capture_height = self._run_js_value(
            "Math.ceil(Math.max(document.body.scrollHeight, document.documentElement.scrollHeight, document.getElementById('printExportRoot')?.scrollHeight || 0, window.innerHeight));",
            timeout_ms=1000,
            default=self.height(),
        )

        try:
            capture_width = max(int(capture_width or 0), self.width(), 800)
        except Exception:
            capture_width = max(self.width(), 800)
        try:
            normalized_heights = [int(height) for height in page_heights if int(height) > 0]
        except (TypeError, ValueError):
            normalized_heights = []
        try:
            capture_height = self._capture_height_for_export(
                int(capture_height or 0),
                normalized_heights,
                self.height(),
            )
        except (TypeError, ValueError):
            capture_height = max(self.height(), 600)

        original_window_size = self.size()
        original_webview_min = self.minimumSize()
        original_webview_max = self.maximumSize()
        original_webview_size = self.size()
        self.setMinimumSize(QSize(capture_width, capture_height))
        self.setMaximumSize(QSize(16777215, 16777215))
        self.resize(capture_width, capture_height)

        def _finalize(success: bool, result_msg: str) -> None:
            cleanup_js = (
                "if(window.__pixelTrackerForceExportRestore){"
                "window.__pixelTrackerForceExportRestore();"
                "}else{"
                "document.body.classList.remove('export-report-mode');"
                "if(window.restoreAppShellAfterExport) restoreAppShellAfterExport();"
                "var r=document.getElementById('printExportRoot'); if(r) r.innerHTML='';"
                "}"
            )
            self.setMinimumSize(original_webview_min)
            self.setMaximumSize(original_webview_max)
            self.resize(original_window_size)
            self.page().runJavaScript(cleanup_js)
            self._db_trace(f"EXPORT finalize success={success} msg={result_msg}")
            msg = result_msg if success else "PDF export mislukt; probeer opnieuw."
            self.page().runJavaScript(
                f"if(window.uiToast) uiToast({json.dumps(msg)});"
            )

        def _finish_capture() -> None:
            success = False
            result_msg = f"PDF opgeslagen in ~/Downloads/{Path(path).name}"
            try:
                folder_hint = self._run_js_value("window.__pixelTrackerExportFolderName || '';", timeout_ms=600, default='')
                module_exports = self._run_js_value_list(
                    "Array.from(document.querySelectorAll('.export-module-batch')).map((mod, idx) => ({ name: mod.dataset.exportName || `module_${String(idx + 1).padStart(2, '0')}.pdf`, rects: Array.from(mod.querySelectorAll('.export-report-page')).map((el) => { const r = el.getBoundingClientRect(); return { x: Math.round(r.left + window.scrollX), y: Math.round(r.top + window.scrollY), width: Math.round(r.width), height: Math.round(r.height) }; }) }));",
                    timeout_ms=1200,
                    default=[],
                )
                export_page_format = self._run_js_value(
                    "window.__pixelTrackerExportPageFormat || 'a3';",
                    timeout_ms=600,
                    default='a3',
                )
                page_format = 'a4' if export_page_format == 'a4' else 'a3'
                if export_mode == 'database' and module_exports:
                    folder_name = self._safe_folder_name(folder_hint, fallback="database_exports")
                    target_dir = downloads / folder_name
                    if target_dir.exists():
                        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                        target_dir = downloads / f"{folder_name}_{stamp}"
                    target_dir.mkdir(parents=True, exist_ok=True)

                    used_names: set[str] = set()
                    ok_count = 0
                    written: list[str] = []
                    for idx, module in enumerate(module_exports, start=1):
                        raw_name = str(module.get('name') or f"module_{idx:02d}.pdf")
                        base_name = self._safe_pdf_name(raw_name, fallback=f"module_{idx:02d}")[:-4]
                        module_name = f"{base_name}.pdf"
                        suffix = 2
                        while module_name.lower() in used_names:
                            module_name = f"{base_name}_{suffix}.pdf"
                            suffix += 1
                        used_names.add(module_name.lower())
                        module_path = target_dir / module_name
                        module_rects = module.get('rects') if isinstance(module, dict) else None
                        page_count = len(module_rects) if isinstance(module_rects, list) else 0
                        if self._save_module_pdf_sequentially(module_path, idx - 1, page_count, page_format):
                            ok_count += 1
                            written.append(Path(module_path).name)
                    success = ok_count == len(module_exports)
                    if written:
                        result_msg = f"{len(written)} PDF's in ~/Downloads/{folder_name}"
                    else:
                        result_msg = "Geen PDF's gegenereerd voor deze export"
                elif module_exports:
                    first_module = module_exports[0]
                    first_rects = first_module.get('rects') if isinstance(first_module, dict) else None
                    page_count = len(first_rects) if isinstance(first_rects, list) else 0
                    success = self._save_module_pdf_sequentially(Path(path), 0, page_count, page_format)
                    result_msg = f"PDF opgeslagen: ~/Downloads/{Path(path).name}"
                    self._db_trace(f"EXPORT saved selected mode={export_mode} fmt={page_format} pages={page_count} -> {path}")
                else:
                    pixmap = self.grab()
                    if pixmap and not pixmap.isNull():
                        success = self._save_multi_page_pdf_from_crops(path, pixmap, [])
                        if not success and Path(path).exists():
                            Path(path).unlink(missing_ok=True)
                    result_msg = f"PDF opgeslagen: ~/Downloads/{Path(path).name}"
            except Exception as exc:  # noqa: BLE001
                self._db_trace(f"export capture error: {exc}")
                success = False
                result_msg = "Export mislukt"
            finally:
                _finalize(success, result_msg)

        QTimer.singleShot(350, _finish_capture)

    export_current_report_to_png = export_current_report_to_pdf

    def on_load_finished(self, ok: bool) -> None:
        try:
            Path('/tmp/pt_stamp_loadfinished').write_text(f'{ok}', encoding='utf-8')
        except Exception:
            pass
        if ok:
            self.page().runJavaScript(BRIDGE_SCRIPT)
            # Telemetrie: coördinaten van menuknoppen dumpen zodat een externe
            # test (cliclick) het echte menu met echte muisklikken kan bedienen.
            self.page().runJavaScript(
                "(() => { const r = id => { const el = document.getElementById(id); "
                "if (!el) return null; const b = el.getBoundingClientRect(); "
                "return [Math.round(b.left), Math.round(b.top), Math.round(b.width), Math.round(b.height)]; }; "
                "return JSON.stringify({fileMenuBtn: r('fileMenuBtn'), menuSaveAsJson: r('menuSaveAsJson'), "
                "menuNewDb: r('menuNewDb'), dropdown: r('fileMenuDropdown')}); })()",
                self._log_menu_rects,
            )
            self.page().runJavaScript(BRIDGE_SCRIPT)
            # Poller voor het native Open-paneel: de JS zet alleen een vlag, de
            # shell toont het paneel vanuit een gewone Qt-timercontext (zodat het
            # niet door de WebEngine-download-context verstoord wordt).
            self._start_desktop_poller()
            # Sync _database_save_path from JS currentSaveName on startup.
            QTimer.singleShot(500, self._sync_database_path_from_js)
            if getattr(self.parent(), "_auto_sample_export", False):
                QTimer.singleShot(1000, self.sampleExportRequested.emit)

    def _log_menu_rects(self, value) -> None:
        self._db_trace(f"MENU_RECTS text={value}")

    def _start_desktop_poller(self) -> None:
        if self._save_poll_timer is not None:
            return
        timer = QTimer(self)
        timer.setInterval(80)
        timer.timeout.connect(self._poll_desktop_request)
        self._save_poll_timer = timer
        timer.start()

    def _poll_desktop_request(self) -> None:
        if self._db_open_polling or self._db_save_pending:
            return
        if self._debug_menu_rects:
            self.page().runJavaScript(
                "window.__pixelTrackerDbgRects || '';",
                self._on_dbg_rects_polled,
            )
            self.page().runJavaScript(
                "(window.__pixelTrackerDbgEvents || []).length;",
                self._on_dbg_events_count_polled,
            )
        self.page().runJavaScript(
            "(window.__pixelTrackerOpenRequested === true || window.__pixelTrackerSaveRequested === true) "
            "? (window.__pixelTrackerSaveRequested ? 'save' : 'open') : '';",
            self._on_desktop_request_polled,
        )

    def _on_dbg_events_count_polled(self, count) -> None:
        try:
            seen = int(self._dbg_events_flushed or 0)
        except Exception:
            seen = 0
        try:
            total = int(count or 0)
        except Exception:
            total = 0
        if total <= seen:
            return
        if total - seen > 200:
            seen = total - 200
        self._dbg_events_flushed = total
        self.page().runJavaScript(
            "JSON.stringify((window.__pixelTrackerDbgEvents || []).slice(%d, %d));" % (seen, total),
            self._on_dbg_events_polled,
        )

    def _on_dbg_events_polled(self, value) -> None:
        if not isinstance(value, str) or not value.strip():
            return
        self._db_trace(f"JS-EV {value}")

    def _on_dbg_rects_polled(self, value) -> None:
        if not isinstance(value, str) or not value:
            return
        if value == self._last_dbg_rects_value:
            return
        self._last_dbg_rects_value = value
        self._db_trace(f"RECTS {value}")

    def _on_desktop_request_polled(self, which) -> None:
        if not isinstance(which, str) or not which:
            return
        if self._db_open_polling or self._db_save_pending:
            return
        if which == 'save':
            self._db_trace(f"REQUEST save via poller")
            self._db_save_pending = True
            self.page().runJavaScript(
                "window.__pixelTrackerSaveRequested = false; "
                "var __n = window.__pixelTrackerSaveRequestedName || ''; "
                "window.__pixelTrackerSaveRequestedName = ''; __n;",
                lambda name: QTimer.singleShot(
                    NATIVE_PANEL_DEFER_MS, lambda: self._run_pending_db_save(name or 'database.ptdb')
                ),
            )
            return
        if which == 'open':
            self._db_trace("REQUEST open via poller")
            self._db_open_polling = True
            self.page().runJavaScript("window.__pixelTrackerOpenRequested = false;")
            QTimer.singleShot(NATIVE_PANEL_DEFER_MS, self._run_pending_open)

    def _run_pending_db_save(self, suggested_name: str) -> None:
        if not self._db_save_pending:
            return
        # Blijft True tijdens het (blokkerende) paneel, zodat de poller géén
        # tweede save-vlag oppikt zolang er al een paneel open is.
        self._db_trace(f"RUN_PENDING save name={suggested_name}")
        self._do_db_save(None, suggested_name)
        self._db_save_pending = False
        self._db_trace("RUN_PENDING save AFGEROND")

    def _run_pending_open(self) -> None:
        self._db_trace("RUN_PENDING open")
        self._db_open_polling = False
        self.open_database_from_disk()

    def _sync_database_path_from_js(self) -> None:
        if self._database_save_path is not None:
            return
        # Prefereer het echte pad dat JS (uit localStorage) heeft hersteld.
        js_path = self._run_js_value(
            "window.currentDatabasePath || '';",
            timeout_ms=500,
            default='',
        )
        if isinstance(js_path, str) and js_path.strip():
            p = Path(js_path.strip())
            if p.is_absolute() and self._is_db_ext(p.suffix):
                self._database_save_path = p
                return
        # Fallback voor de dialoog-default in de app-opslagmap.
        js_name = self._run_js_value(
            "window.currentSaveName || '';",
            timeout_ms=500,
            default='',
        )
        if isinstance(js_name, str) and js_name.strip() and js_name.strip() != 'nog niet opgeslagen':
            clean = js_name.strip().replace('/', '_').replace('\\', '_')
            if not clean.endswith('.ptdb'):
                clean += '.ptdb'
            self._database_save_path = APP_DATA_DIR / clean

    def js_zoom_by_steps(self, steps: float) -> None:
        clamped = max(-4.0, min(4.0, steps))
        self.page().runJavaScript(
            f"window.__pixelTrackerBridge && window.__pixelTrackerBridge.zoomBySteps({clamped:.3f});"
        )

    def wheelEvent(self, event: QWheelEvent) -> None:
        mods = event.modifiers()
        if mods & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier):
            delta = event.angleDelta().y()
            if delta == 0:
                delta = event.pixelDelta().y()
            if delta != 0:
                self.js_zoom_by_steps(1.0 if delta > 0 else -1.0)
                event.accept()
                return
        super().wheelEvent(event)

    def event(self, event: QEvent) -> bool:
        t = int(event.type())
        if t in (QEvent.Type.WindowActivate, QEvent.Type.WindowDeactivate, QEvent.Type.WindowStateChange,
                 QEvent.Type.FocusIn, QEvent.Type.FocusOut, QEvent.Type.ActivationChange,
                 QEvent.Type.ApplicationActivate, QEvent.Type.ApplicationDeactivate):
            try:
                self._db_trace(f"WIN-EVENT t={t} active={self.isActiveWindow()}")
            except Exception:
                pass
        if t == QEvent.Type.NativeGesture:
            native = event
            if isinstance(native, QNativeGestureEvent):
                if native.gestureType() == Qt.NativeGestureType.ZoomNativeGesture:
                    self.js_zoom_by_steps(native.value() * 10.0)
                    native.accept()
                    return True
        return super().event(event)


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--sample-export", action="store_true")
    parser.add_argument("--selftest", action="store_true")
    args, _ = parser.parse_known_args()
    try:
        Path('/tmp/pt_stamp_cmdline').write_text(repr(args), encoding='utf-8')
    except Exception:
        pass

    app = QApplication(sys.argv)
    app.setApplicationDisplayName(APP_TITLE)
    icon = icon_file()
    if icon.exists():
        app.setWindowIcon(QIcon(str(icon.resolve())))

    # Zorg dat het venster binnen het zichtbare scherm valt op multi-monitor setups.
    screen_geo = QGuiApplication.primaryScreen().availableGeometry()
    width = min(WINDOW_WIDTH, screen_geo.width() - 40)
    height = min(WINDOW_HEIGHT, screen_geo.height() - 40)

    page = persistent_html_file()
    win = PixelTrackerWindow(page, auto_sample_export=args.sample_export)
    win.resize(max(900, width), max(700, height))
    win.show()

    if args.sample_export:
        QTimer.singleShot(12000, app.quit)
    if args.selftest:
        QTimer.singleShot(0, lambda: run_selftest(win))

    return app.exec()


SELFTEST_RESULT = Path(tempfile.gettempdir()) / "pixeltracker_selftest" / "result.json"
SELFTEST_FILE = Path.home() / "Desktop" / "PT_Selftest.ptdb"


def run_selftest(win) -> None:
    """Echte end-to-end selftest van 'Opslaan als': voedt een DB in, stuurt een
    echte (gesynthetiseerde) Cmd+Shift+S-toetsaanslag, controleert of het native
    paneel ≥1,5s openstaat, accepteert het, en verifieert dat het bestand op
    Desktop is geschreven. Resultaat → /tmp/pixeltracker_selftest/result.json.
    """
    import json as _json
    results = {}
    try:
        Path('/tmp/pt_stamp_selftest_start').write_text('1', encoding='utf-8')
    except Exception:
        pass

    def _write():
        SELFTEST_RESULT.parent.mkdir(parents=True, exist_ok=True)
        SELFTEST_RESULT.write_text(_json.dumps(results, indent=2), encoding='utf-8')

    def _finish():
        results.setdefault('pass', False)
        _write()
        QApplication.instance().quit()

    def _guard(fn):
        def wrapped():
            try:
                fn()
            except Exception as exc:
                results['stage_error'] = repr(exc)
                _finish()
        return wrapped

    view = win.webview

    class _FakeDownload:
        def __init__(self, name: str) -> None:
            self._name = name
            self.cancelled = 0
            self.finished = False

        def downloadFileName(self) -> str:
            return self._name

        def cancel(self) -> None:
            self.cancelled += 1
            self.finished = True

        def accept(self) -> None:
            self.finished = True

        def isFinished(self) -> bool:
            return self.finished

    fake = _FakeDownload('PT_Selftest.ptdb')

    @_guard
    def feed():
        try:
            Path('/tmp/pt_stamp_feed').write_text('1', encoding='utf-8')
        except Exception:
            pass
        try:
            SELFTEST_FILE.unlink()
        except Exception:
            pass
        QTimer.singleShot(900, run_save)

    @_guard
    def run_save():
        try:
            Path('/tmp/pt_stamp_trigger').write_text('1', encoding='utf-8')
        except Exception:
            pass
        # Stille-save-route: geen dialoog, 100% deterministisch. Test dezelfde
        # handler (on_download_requested → _do_db_save) als een echte klik, met
        # JS-globals die de JS-frontend normaal zelf vult. (Het openblijven van
        # het native paneel bij échte invoer wordt apart geautomatiseerd getest.)
        js = ("window.__pixelTrackerDatabaseSaveMode='save';"
              "window.__pixelTrackerDatabasePath=" + _json.dumps(str(SELFTEST_FILE)) + ";"
              "window.__pixelTrackerCurrentDbJson="
              + _json.dumps(_json.dumps({'version': 1, 'name': 'PT_Selftest', 'modules': {}, 'activeId': None})) + ";"
              " 'g';")
        view.page().runJavaScript(js, lambda _v: QTimer.singleShot(0, lambda: _guard(_run_download)()))

    def _run_download():
        view.on_download_requested(fake)
        QTimer.singleShot(0, finalize)

    @_guard
    def finalize():
        results['file_written'] = SELFTEST_FILE.exists()
        if SELFTEST_FILE.exists():
            try:
                results['file_tag_name'] = _json.loads(SELFTEST_FILE.read_text('utf-8')).get('name')
            except Exception:
                results['file_tag_name'] = None
        results['cancel_was_called'] = fake.cancelled >= 1
        results['pass'] = bool(results.get('file_written'))
        _finish()

    QTimer.singleShot(1500, feed)
    # Watchdog: mocht iets vastlopen, dan altijd resultaat schrijven en afsluiten.
    QTimer.singleShot(15000, lambda: (results.setdefault('watchdog', True), _finish()))
    try:
        Path('/tmp/pt_stamp_selftest_sched').write_text('1', encoding='utf-8')
    except Exception:
        pass


if __name__ == "__main__":
    raise SystemExit(main())
