import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch


class HtmlPathTests(unittest.TestCase):
    @staticmethod
    def load_desktop_module():
        repo_root = Path(__file__).resolve().parents[1]
        module_path = repo_root / "src" / "pixel_repair_desktop.py"
        spec = importlib.util.spec_from_file_location("pixel_repair_desktop", module_path)
        if spec is None or spec.loader is None:
            raise RuntimeError("Could not load pixel_repair_desktop")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_html_file_finds_repo_asset(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        module_path = repo_root / "src" / "pixel_repair_desktop.py"

        spec = importlib.util.spec_from_file_location("pixel_repair_desktop", module_path)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        html_path = module.html_file()

        self.assertTrue(html_path.exists(), msg=f"Expected HTML asset at {html_path}")
        self.assertEqual(html_path.name, "pixel_repair_app.html")

    def test_macos_app_data_path(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        module_path = repo_root / "src" / "pixel_repair_desktop.py"
        spec = importlib.util.spec_from_file_location("pixel_repair_desktop", module_path)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        expected = Path.home() / "Library" / "Application Support" / "PixelTracker"
        self.assertEqual(module.app_data_dir(), expected)

    def test_windows_app_data_path_uses_local_app_data(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        module_path = repo_root / "src" / "pixel_repair_desktop.py"
        spec = importlib.util.spec_from_file_location("pixel_repair_desktop", module_path)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        with patch.object(module.sys, "platform", "win32"), patch.dict(
            module.os.environ, {"LOCALAPPDATA": r"C:\Users\Tester\AppData\Local"}
        ):
            self.assertEqual(
                module.app_data_dir(),
                Path(r"C:\Users\Tester\AppData\Local") / "PixelTracker",
            )

    def test_database_export_capture_height_is_bounded_to_one_module(self) -> None:
        module = self.load_desktop_module()

        height = module.PixelTrackerWebView._capture_height_for_export(
            full_height=120_000, page_heights=[1123, 1123, 1123], viewport_height=940
        )

        self.assertEqual(height, 1123)

    def test_selected_export_capture_height_is_also_bounded_to_one_page(self) -> None:
        module = self.load_desktop_module()

        height = module.PixelTrackerWebView._capture_height_for_export(
            full_height=6800, page_heights=[1123, 1123], viewport_height=940
        )

        self.assertEqual(height, 1123)

    def test_desktop_database_save_tracks_current_path_and_uses_atomic_replace(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        source = (repo_root / "src" / "pixel_repair_desktop.py").read_text(encoding="utf-8")

        self.assertIn("self._database_save_path: Path | None = None", source)
        self.assertIn("window.__pixelTrackerDatabaseSaveMode", source)
        self.assertIn("os.replace(temp_path, target_path)", source)


if __name__ == "__main__":
    unittest.main()
