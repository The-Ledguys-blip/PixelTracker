# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['../src/pixel_repair_desktop.py'],
    pathex=[],
    binaries=[],
    datas=[('../assets/pixel_repair_app.html', '.'), ('../assets/app_icon.png', '.')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='PixelTracker',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['../assets/app_icon.icns'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='PixelTracker',
)
app = BUNDLE(
    coll,
    name='PixelTracker.app',
    icon='../assets/app_icon.icns',
    bundle_identifier='com.pixeltracker.app',
    version='3.0.23',
    info_plist={
        'CFBundleDisplayName': 'PixelTracker',
        'CFBundleShortVersionString': '3.0.23',
        'CFBundleVersion': '3.0.23',
        'LSMinimumSystemVersion': '12.0',
        'NSHighResolutionCapable': True,
    },
)
