import unittest
from pathlib import Path


class ExportPreviewLayoutTests(unittest.TestCase):
    def test_beta_startup_choice_and_empty_preset_migration(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        html = (repo_root / "assets" / "pixel_repair_app.html").read_text(encoding="utf-8")
        spec = (repo_root / "build" / "PixelTracker.spec").read_text(encoding="utf-8")

        self.assertIn('id="startupChoiceOverlay"', html)
        self.assertIn('id="startupNewFileBtn"', html)
        self.assertIn('id="startupRestoreSessionBtn"', html)
        self.assertIn("const startupRestoreState = load();", html)
        self.assertIn("if (!startupChoicePending)", html)
        self.assertIn("pixelRepairApp_betaPresetReset_v2_1_28", html)
        self.assertIn("const emptyLibrary = JSON.stringify(defaultLibrary());", html)
        self.assertIn("version='2.1.32'", spec)
        self.assertIn("'CFBundleShortVersionString': '2.1.32'", spec)

    def test_desktop_export_runs_without_page_navigation(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        html = (repo_root / "assets" / "pixel_repair_app.html").read_text(encoding="utf-8")

        self.assertNotIn("window.location.href = 'pixeltracker://export'", html)
        self.assertEqual(html.count("if (isDesktop) {\n          window.print();"), 1)
        self.assertEqual(html.count("if (isDesktop) {\n        window.print();"), 1)

    def test_module_context_menu_supports_all_edit_actions(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        html = (repo_root / "assets" / "pixel_repair_app.html").read_text(encoding="utf-8")

        self.assertIn('id="ctxEditNameBtn" data-action="name"', html)
        self.assertIn('id="ctxEditTypeBtn" data-action="type"', html)
        self.assertIn('id="ctxEditSerialBtn" data-action="serial"', html)
        self.assertIn('id="ctxDeleteBtn" data-action="delete"', html)
        self.assertIn("moduleContextMenu.addEventListener('pointerdown'", html)
        self.assertIn("else if (action === 'serial') scanUpdateSn(id);", html)
        self.assertIn("moduleContextMenu.classList.add('show');", html)

    def test_windows_installer_contract(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        windows_spec = (repo_root / "build" / "PixelTracker-Windows.spec").read_text(encoding="utf-8")
        version_info = (repo_root / "build" / "version_info_windows.txt").read_text(encoding="utf-8")
        installer = (repo_root / "installer" / "PixelTracker-Windows.iss").read_text(encoding="utf-8")
        build_script = (repo_root / "build_windows.ps1").read_text(encoding="utf-8")
        msi_definition = (repo_root / "installer" / "PixelTracker-Windows.wxs").read_text(encoding="utf-8")
        msi_build_script = (repo_root / "build_msi.ps1").read_text(encoding="utf-8")
        workflow = (repo_root / ".github" / "workflows" / "build-windows.yml").read_text(encoding="utf-8")

        self.assertTrue((repo_root / "assets" / "app_icon.ico").exists())
        self.assertIn("name='PixelTracker-Windows'", windows_spec)
        self.assertIn("PROJECT_ROOT / 'assets' / 'app_icon.ico'", windows_spec)
        self.assertIn("Path(SPECPATH) / 'version_info_windows.txt'", windows_spec)
        self.assertIn("ProductVersion', '2.1.32 Beta'", version_info)
        self.assertIn("DefaultDirName={localappdata}\\Programs\\{#AppName}", installer)
        self.assertIn("PrivilegesRequired=lowest", installer)
        self.assertIn("PixelTracker_V2.1.32_Beta_Windows11_Setup", installer)
        self.assertIn("build\\PixelTracker-Windows.spec", build_script)
        self.assertIn('Version="2.1.32"', msi_definition)
        self.assertIn('InstallScope="perUser"', msi_definition)
        self.assertIn('UpgradeCode="4DF480CF-428E-4FC6-B03D-0C71D27AC9C7"', msi_definition)
        self.assertIn('SourceFile="assets\\app_icon.ico"', msi_definition)
        self.assertIn("heat.exe", msi_build_script)
        self.assertIn("-ag -sfrag", msi_build_script)
        self.assertIn("PixelTracker_V2.1.32_Beta_Windows11.msi", msi_build_script)
        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn("runs-on: windows-2022", workflow)
        self.assertIn("dist/PixelTracker_V2.1.32_Beta_Windows11_Setup.exe", workflow)
        self.assertIn("dist/PixelTracker_V2.1.32_Beta_Windows11.msi", workflow)

    def test_quick_repair_shortcuts_and_build_version(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        html_path = repo_root / "assets" / "pixel_repair_app.html"
        html = html_path.read_text(encoding="utf-8")

        self.assertIn("Build V2.1.32 Beta", html)
        self.assertIn("const BUILD_VERSION = 'V2.1.32 Beta';", html)
        self.assertIn("key !== '1' && key !== '2' && key !== '3'", html)
        self.assertIn("quickAddRepair('Nieuwe Pixel gezet', '#e6007e')", html)
        self.assertIn("quickAddRepair('Pad Paper Gebruikt', '#2563eb')", html)
        self.assertIn("quickAddRepair('Trace gemaakt', '#f59e0b')", html)

    def test_export_preview_uses_shader_segment_groups(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        html_path = repo_root / "assets" / "pixel_repair_app.html"
        html = html_path.read_text(encoding="utf-8")

        self.assertIn("function buildSegmentGroups(m) {", html)
        self.assertIn("const segmentStartX = Math.floor(x / shaderW) * shaderW;", html)
        self.assertIn("const segmentStartY = Math.floor(y / shaderH) * shaderH;", html)
        self.assertIn("function buildSegmentReportPage(m, segment, dark, index, total, isDemoSample) {", html)
        self.assertIn("const stack = document.createElement('div');", html)
        self.assertIn("stack.className = 'export-report-stack';", html)
        self.assertIn("const detailGridW = segmentW;", html)
        self.assertIn("const detailGridH = segmentH;", html)
        self.assertIn("const shaderCellW = segmentW * moduleCell;", html)
        self.assertIn("const shaderCellH = segmentH * moduleCell;", html)
        self.assertIn("const moduleCanvasSize = 300;", html)

    def test_export_preview_matches_required_dual_canvas_layout(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        html_path = repo_root / "assets" / "pixel_repair_app.html"
        html = html_path.read_text(encoding="utf-8")

        self.assertIn("Detail", html)
        self.assertIn("Module Overview", html)
        self.assertIn("export-repairs-table", html)
        self.assertIn("grid-template-columns: 1.32fr 0.88fr;", html)
        self.assertIn("moduleCanvasSize = 300;", html)
        self.assertIn("SEGMENT_EXPORT_FOOTPRINT", html)
        self.assertIn("const displayW = detailBoxSize;", html)
        self.assertIn("const displayH = detailBoxSize;", html)

    def test_export_preview_keeps_segment_footprint_uniform_across_sizes(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        html_path = repo_root / "assets" / "pixel_repair_app.html"
        html = html_path.read_text(encoding="utf-8")

        self.assertIn("const SEGMENT_EXPORT_FOOTPRINT = 500;", html)
        self.assertIn("const canvasSize = 570;", html)
        self.assertIn("const shaderCellW = segmentW * moduleCell;", html)
        self.assertIn("const shaderCellH = segmentH * moduleCell;", html)

    def test_export_preview_applies_header_metadata_style_contract(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        html_path = repo_root / "assets" / "pixel_repair_app.html"
        html = html_path.read_text(encoding="utf-8")

        self.assertIn(".export-title-row-value", html)
        self.assertIn(".export-report-meta-inline", html)
        self.assertIn("border-radius: 999px;", html)


if __name__ == "__main__":
    unittest.main()
