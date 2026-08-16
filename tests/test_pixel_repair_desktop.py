import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch


class HtmlPathTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
