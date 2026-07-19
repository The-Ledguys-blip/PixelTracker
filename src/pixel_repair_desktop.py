from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtCore import QEvent, Qt, QUrl
from PyQt6.QtGui import QGuiApplication, QIcon, QNativeGestureEvent, QWheelEvent
from PyQt6.QtWidgets import QApplication, QMainWindow
from PyQt6.QtWebEngineWidgets import QWebEngineView


APP_TITLE = "PixelTracker"
WINDOW_WIDTH = 1540
WINDOW_HEIGHT = 940


BRIDGE_SCRIPT = r"""
(() => {
    if (window.__pixelTrackerBridge) return;
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
    path = base_path() / "pixel_repair_app.html"
    if not path.exists():
        raise FileNotFoundError(f"HTML bestand niet gevonden: {path}")
    return path


def icon_file() -> Path:
    return base_path() / "app_icon.png"


class PixelTrackerWindow(QMainWindow):
    def __init__(self, page_path: Path) -> None:
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(WINDOW_WIDTH, WINDOW_HEIGHT)

        icon = icon_file()
        if icon.exists():
            self.setWindowIcon(QIcon(str(icon.resolve())))

        self.webview = PixelTrackerWebView(self)
        self.setCentralWidget(self.webview)
        self.webview.load(QUrl.fromLocalFile(str(page_path.resolve())))


class PixelTrackerWebView(QWebEngineView):
    def __init__(self, parent: QMainWindow | None = None) -> None:
        super().__init__(parent)
        self.page().loadFinished.connect(self.on_load_finished)

    def on_load_finished(self, ok: bool) -> None:
        if ok:
            self.page().runJavaScript(BRIDGE_SCRIPT)

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
    app = QApplication(sys.argv)
    app.setApplicationDisplayName(APP_TITLE)
    icon = icon_file()
    if icon.exists():
        app.setWindowIcon(QIcon(str(icon.resolve())))

    # Zorg dat het venster binnen het zichtbare scherm valt op multi-monitor setups.
    screen_geo = QGuiApplication.primaryScreen().availableGeometry()
    width = min(WINDOW_WIDTH, screen_geo.width() - 40)
    height = min(WINDOW_HEIGHT, screen_geo.height() - 40)

    page = html_file()
    win = PixelTrackerWindow(page)
    win.resize(max(900, width), max(700, height))
    win.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
