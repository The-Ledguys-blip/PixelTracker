import unittest
from pathlib import Path


class ExportPreviewLayoutTests(unittest.TestCase):
    def get_release_version(self) -> str:
        repo_root = Path(__file__).resolve().parents[1]
        return (repo_root / "VERSION").read_text(encoding="utf-8").strip()

    def test_beta_startup_choice_and_empty_preset_migration(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        html = (repo_root / "assets" / "pixel_repair_app.html").read_text(encoding="utf-8")
        spec = (repo_root / "build" / "PixelTracker.spec").read_text(encoding="utf-8")
        version = self.get_release_version()

        self.assertIn('id="startupChoiceOverlay"', html)
        self.assertIn('id="startupNewFileBtn"', html)
        self.assertIn('id="startupRestoreSessionBtn"', html)
        self.assertIn("const startupRestoreState = load();", html)
        self.assertIn("if (!startupChoicePending)", html)
        self.assertIn("pixelRepairApp_betaPresetReset_v2_1_28", html)
        self.assertIn("const emptyLibrary = JSON.stringify(defaultLibrary());", html)
        self.assertIn(f"version='{version}'", spec)
        self.assertIn(f"'CFBundleShortVersionString': '{version}'", spec)

    def test_desktop_export_runs_without_page_navigation(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        html = (repo_root / "assets" / "pixel_repair_app.html").read_text(encoding="utf-8")

        self.assertNotIn("window.location.href = 'pixeltracker://export'", html)
        self.assertEqual(html.count("if (isDesktop) {\n          window.print();"), 1)
        self.assertEqual(html.count("if (isDesktop) {\n        window.print();"), 1)

    def test_browser_export_falls_back_to_print_dialog_with_hint(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        html = (repo_root / "assets" / "pixel_repair_app.html").read_text(encoding="utf-8")

        self.assertIn("Browser export fallback", html)
        self.assertIn("Save as PDF", html)
        self.assertIn("window.print();", html)

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

    def test_undo_menu_exposes_manual_history_controls(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        html = (repo_root / "assets" / "pixel_repair_app.html").read_text(encoding="utf-8")

        self.assertIn('id="menuUndo"', html)
        self.assertIn('id="menuRedo"', html)
        self.assertIn('Ongedaan maken', html)
        self.assertIn('Opnieuw', html)
        self.assertIn('syncUndoMenuState()', html)

    def test_undo_shortcut_requires_confirmation_before_reverting(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        html = (repo_root / "assets" / "pixel_repair_app.html").read_text(encoding="utf-8")

        self.assertIn("Wil je de laatste wijziging echt ongedaan maken?", html)
        self.assertIn("confirmUndoAction('undo', undo)", html)

    def test_windows_installer_contract(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        windows_spec = (repo_root / "build" / "PixelTracker-Windows.spec").read_text(encoding="utf-8")
        version_info = (repo_root / "build" / "version_info_windows.txt").read_text(encoding="utf-8")
        installer = (repo_root / "installer" / "PixelTracker-Windows.iss").read_text(encoding="utf-8")
        build_script = (repo_root / "build_windows.ps1").read_text(encoding="utf-8")
        msi_definition = (repo_root / "installer" / "PixelTracker-Windows.wxs").read_text(encoding="utf-8")
        msi_build_script = (repo_root / "build_msi.ps1").read_text(encoding="utf-8")
        workflow = (repo_root / ".github" / "workflows" / "build-windows.yml").read_text(encoding="utf-8")
        version = self.get_release_version()
        version_label = f"{version} Beta"

        self.assertTrue((repo_root / "assets" / "app_icon.ico").exists())
        self.assertIn("name='PixelTracker-Windows'", windows_spec)
        self.assertIn("PROJECT_ROOT / 'assets' / 'app_icon.ico'", windows_spec)
        self.assertIn("Path(SPECPATH) / 'version_info_windows.txt'", windows_spec)
        self.assertIn(f"ProductVersion', '{version_label}'", version_info)
        self.assertIn("DefaultDirName={localappdata}\\Programs\\{#AppName}", installer)
        self.assertIn("PrivilegesRequired=lowest", installer)
        self.assertIn(f"PixelTracker_V{version_label.replace(' ', '_')}_Windows11_Setup", installer)
        self.assertIn("build\\PixelTracker-Windows.spec", build_script)
        self.assertIn(f'Version="{version}"', msi_definition)
        self.assertIn('InstallScope="perUser"', msi_definition)
        self.assertIn('UpgradeCode="4DF480CF-428E-4FC6-B03D-0C71D27AC9C7"', msi_definition)
        self.assertIn('SourceFile="assets\\app_icon.ico"', msi_definition)
        self.assertIn("heat.exe", msi_build_script)
        self.assertIn("-ag -sfrag -srd -sreg", msi_build_script)
        self.assertIn("-sice:ICE38 -sice:ICE64 -sice:ICE91", msi_build_script)
        self.assertIn("if ($LASTEXITCODE -ne 0)", msi_build_script)
        self.assertIn(f"PixelTracker_V{version_label.replace(' ', '_')}_Windows11.msi", msi_build_script)
        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn("runs-on: windows-2022", workflow)
        self.assertIn(f"dist/PixelTracker_V{version_label.replace(' ', '_')}_Windows11_Setup.exe", workflow)
        self.assertIn(f"dist/PixelTracker_V{version_label.replace(' ', '_')}_Windows11.msi", workflow)

    def test_quick_repair_shortcuts_and_build_version(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        html_path = repo_root / "assets" / "pixel_repair_app.html"
        html = html_path.read_text(encoding="utf-8")
        version_label = f"{self.get_release_version()} Beta"

        self.assertIn(f"Build V{version_label}", html)
        self.assertIn(f"const BUILD_VERSION = 'V{version_label}';", html)
        self.assertIn("key !== '1' && key !== '2' && key !== '3'", html)
        self.assertIn("quickAddRepair('Nieuwe Pixel gezet', '#e6007e')", html)
        self.assertIn("quickAddRepair('Pad Paper Gebruikt', '#2563eb')", html)
        self.assertIn("quickAddRepair('Trace gemaakt', '#f59e0b')", html)

    def test_database_save_uses_stable_name_and_distinct_save_modes(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        html = (repo_root / "assets" / "pixel_repair_app.html").read_text(encoding="utf-8")

        self.assertIn("a.download = base + DB_EXT;", html)
        self.assertNotIn("a.download = `${base}_${timestampCompact()}.json`;", html)
        self.assertIn("DB_EXT = '.ptdb';", html)
        self.assertIn("exportDatabaseJson(currentSaveName, 'save')", html)
        self.assertIn("exportDatabaseJson(currentSaveName, 'save_as')", html)

    def test_single_selected_pixel_supports_arrow_key_navigation(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        html = (repo_root / "assets" / "pixel_repair_app.html").read_text(encoding="utf-8")

        self.assertIn("ArrowLeft: [-1, 0]", html)
        self.assertIn("ArrowRight: [1, 0]", html)
        self.assertIn("ArrowUp: [0, -1]", html)
        self.assertIn("ArrowDown: [0, 1]", html)
        self.assertIn("selected.size !== 1", html)
        self.assertIn("e.preventDefault();", html)
        self.assertIn("keepSelectedPixelInView(nextX, nextY);", html)

    def test_session_counts_only_active_session_repairs_while_keeping_history_visible(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        html = (repo_root / "assets" / "pixel_repair_app.html").read_text(encoding="utf-8")

        self.assertIn("const visibleRepairs = repairs || [];", html)
        self.assertIn("const countedRepairs = activeSession ? getSessionFilteredRepairs(visibleRepairs, activeSession) : visibleRepairs;", html)
        self.assertIn("renderRepairFilterOptions(visibleRepairs);", html)

    def test_all_session_keeps_database_modules_visible_without_session_assignment(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        html = (repo_root / "assets" / "pixel_repair_app.html").read_text(encoding="utf-8")

        self.assertIn("if (!session || isAllSession(session.id)) return Object.values(state.modules || {});", html)
        self.assertIn("if (!session || isAllSession(session.id)) return Array.isArray(repairs) ? repairs : [];", html)

    def test_module_session_status_badges_are_visible(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        html = (repo_root / "assets" / "pixel_repair_app.html").read_text(encoding="utf-8")

        self.assertIn("module-session-badge", html)
        self.assertIn("Niet gekoppeld", html)
        self.assertIn("ALL", html)
        self.assertIn("Sessie:", html)

    def test_session_export_uses_session_only_branding_and_summary(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        html = (repo_root / "assets" / "pixel_repair_app.html").read_text(encoding="utf-8")

        self.assertIn("Pixel Tracker Sessie Export", html)
        self.assertIn("Overzicht per type", html)
        self.assertIn("export-repair-dot", html)

    def test_startup_restore_keeps_existing_database_path_for_save(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        html = (repo_root / "assets" / "pixel_repair_app.html").read_text(encoding="utf-8")

        self.assertIn("// Behoud het echte bestandspad zodra er een bestaand bestandspad bekend is.", html)
        self.assertIn("if (!restoredPath) {", html)
        self.assertIn("setCurrentDatabasePath('');", html)

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
        self.assertIn("String(segmentStartX + i)", html)
        self.assertIn("String(segmentStartY + i)", html)
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
