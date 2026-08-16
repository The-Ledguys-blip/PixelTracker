from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from datetime import datetime
import shutil
import argparse

from PyQt6.QtCore import QEvent, QEventLoop, QPoint, QSize, Qt, QTimer, QUrl, pyqtSignal as Signal
from PyQt6.QtGui import QGuiApplication, QIcon, QNativeGestureEvent, QWheelEvent
from PyQt6.QtWidgets import QApplication, QFileDialog, QMainWindow
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineDownloadRequest, QWebEngineProfile, QWebEnginePage, QWebEngineSettings

try:
    from reportlab.lib.pagesizes import A3, landscape
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas as pdf_canvas
    REPORTLAB_AVAILABLE = True
except Exception:
    REPORTLAB_AVAILABLE = False


APP_TITLE = "PixelTracker"
WINDOW_WIDTH = 1540
WINDOW_HEIGHT = 940


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
})();
"""


def base_path() -> Path:
    if hasattr(sys, "_MEIPASS"):
        return Path(getattr(sys, "_MEIPASS"))
    return Path(__file__).resolve().parent


def html_file() -> Path:
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
            root.appendChild(page);
            ok = true;
        }
        if (!ok) return false;
        if (typeof window.__pixelTrackerHideAppShellForExport === 'function') {
            window.__pixelTrackerHideAppShellForExport();
        }
        document.body.classList.add('export-report-mode');
        const now = new Date();
        const pad = (n) => String(n).padStart(2, '0');
        window.__pixelTrackerExportName = `PixelTracker_export_${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}_${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}.pdf`;
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
        if decision in {"discard_close", "close_clean"}:
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
        self.setPage(PixelTrackerPage(self._profile, self))
        self.page().loadFinished.connect(self.on_load_finished)
        self.page().printRequested.connect(self.on_print_requested)

    def on_download_requested(self, download: QWebEngineDownloadRequest) -> None:
        suggested = Path(download.downloadFileName())
        ext = suggested.suffix.lower()
        if ext == '.json':
            filter_str = 'JSON bestanden (*.json)'
        elif ext == '.csv':
            filter_str = 'CSV bestanden (*.csv)'
        else:
            filter_str = 'Alle bestanden (*)'
        default_path = str(Path.home() / 'Desktop' / suggested.name)
        path, _ = QFileDialog.getSaveFileName(
            self, 'Opslaan als', default_path, filter_str
        )
        if not path:
            download.cancel()
            return
        download.setDownloadDirectory(str(Path(path).parent))
        download.setDownloadFileName(Path(path).name)
        download.accept()

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
    def _safe_pdf_name(raw: str, fallback: str = "module") -> str:
        name = str(raw or "").strip()
        if name.lower().endswith('.pdf'):
            name = name[:-4]
        cleaned = ''.join(ch if ch not in '/\\:*?"<>|' else '-' for ch in name).strip(' .')
        if not cleaned:
            cleaned = fallback
        return f"{cleaned}.pdf"

    @staticmethod
    def _safe_folder_name(raw: str, fallback: str = "database_exports") -> str:
        name = str(raw or "").strip()
        cleaned = ''.join(ch if ch not in '/\\:*?"<>|' else '-' for ch in name).strip(' .')
        return cleaned or fallback

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
                tmp_name = tempfile.NamedTemporaryFile(suffix='.png', delete=False).name
                tmp_path = Path(tmp_name)
                temp_files.append(tmp_path)
                if not crop.save(str(tmp_path), 'PNG'):
                    continue
                pdf.drawImage(ImageReader(str(tmp_path)), 0, 0, width=page_width, height=page_height, preserveAspectRatio=True, anchor='c')
                pdf.showPage()
                any_page = True

            if not any_page:
                # Fallback: always write at least one page to avoid invalid 0-page PDFs.
                tmp_name = tempfile.NamedTemporaryFile(suffix='.png', delete=False).name
                tmp_path = Path(tmp_name)
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
            timestamp = datetime.now().strftime("%Y-%m-%d_%H%M")
            name = f"PixelTracker_export_{timestamp}.pdf"
        else:
            if not name.lower().endswith('.pdf'):
                name = Path(name).with_suffix('.pdf').name

        downloads = Path.home() / "Downloads"
        downloads.mkdir(exist_ok=True)
        path = str(downloads / name)
        if self.page() is None:
            return

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
            capture_height = max(int(capture_height or 0), self.height(), 600)
        except Exception:
            capture_height = max(self.height(), 600)

        original_window_size = self.size()
        original_webview_min = self.minimumSize()
        original_webview_max = self.maximumSize()
        original_webview_size = self.size()
        self.setMinimumSize(QSize(capture_width, capture_height))
        self.setMaximumSize(QSize(16777215, 16777215))
        self.resize(capture_width, capture_height)

        def _finalize(success: bool) -> None:
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
            if success:
                self.page().runJavaScript("if(window.uiToast) uiToast('PDF export opgeslagen in Downloads');")
            else:
                self.page().runJavaScript("if(window.uiToast) uiToast('PDF export mislukte; probeer opnieuw.');")

        def _finish_capture() -> None:
            export_mode = self._run_js_value("window.__pixelTrackerExportMode || 'selected';", timeout_ms=600, default='selected')
            folder_hint = self._run_js_value("window.__pixelTrackerExportFolderName || '';", timeout_ms=600, default='')
            module_exports = self._run_js_value_list(
                "Array.from(document.querySelectorAll('.export-module-batch')).map((mod, idx) => ({ name: mod.dataset.exportName || `module_${String(idx + 1).padStart(2, '0')}.pdf`, rects: Array.from(mod.querySelectorAll('.export-report-page')).map((el) => { const r = el.getBoundingClientRect(); return { x: Math.round(r.left + window.scrollX), y: Math.round(r.top + window.scrollY), width: Math.round(r.width), height: Math.round(r.height) }; }) }));",
                timeout_ms=1200,
                default=[],
            )
            rects = self._run_js_value_list(
                "Array.from(document.querySelectorAll('.export-report-page')).map((el) => { const r = el.getBoundingClientRect(); return { x: Math.round(r.left + window.scrollX), y: Math.round(r.top + window.scrollY), width: Math.round(r.width), height: Math.round(r.height) }; });",
                timeout_ms=1200,
                default=[],
            )
            pixmap = self.grab()

            success = False
            if pixmap and not pixmap.isNull():
                if export_mode == 'database' and module_exports:
                    folder_name = self._safe_folder_name(folder_hint, fallback="database_exports")
                    target_dir = downloads / folder_name
                    if target_dir.exists():
                        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                        target_dir = downloads / f"{folder_name}_{stamp}"
                    target_dir.mkdir(parents=True, exist_ok=True)

                    used_names: set[str] = set()
                    ok_count = 0
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
                        if isinstance(module_rects, list) and self._save_multi_page_pdf_from_crops(str(module_path), pixmap, module_rects):
                            ok_count += 1
                        elif module_path.exists():
                            module_path.unlink(missing_ok=True)
                    success = ok_count == len(module_exports)
                else:
                    success = self._save_multi_page_pdf_from_crops(path, pixmap, rects)
                    if not success and Path(path).exists():
                        Path(path).unlink(missing_ok=True)

            _finalize(success)

        QTimer.singleShot(350, _finish_capture)

    export_current_report_to_png = export_current_report_to_pdf

    def on_load_finished(self, ok: bool) -> None:
        if ok:
            self.page().runJavaScript(BRIDGE_SCRIPT)
            if getattr(self.parent(), "_auto_sample_export", False):
                QTimer.singleShot(1000, self.sampleExportRequested.emit)

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
        if event.type() == QEvent.Type.NativeGesture:
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
    args, _ = parser.parse_known_args()

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

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
