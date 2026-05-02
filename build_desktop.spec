# PyInstaller spec for the Doctor Zebra desktop app.
#
# Build:
#   pip install -r requirements.txt pyinstaller
#   # macOS / Linux:
#   pyinstaller build_desktop.spec
#   # Windows (Zebra USB / spooler support pulls in pywin32 from requirements):
#   pyinstaller build_desktop.spec
#
# Output: dist/DoctorZebra.exe  (Windows)  or  dist/DoctorZebra.app  (macOS)
#
# Layout when frozen
# ------------------
# The bundle ships the read-only assets:
#   - templates/, static/         Flask templates and static files
#   - zebra/                      App package (auto-collected as Python modules)
#   - seed_profiles/default/      Skeleton copied to the user dir on first run
#
# User-writable state lives in ``~/.doctor_zebra/`` (see desktop.py):
#   - profiles/<name>/config.cfg, labels.db, templates_zpl/
#   - app.log

# -*- mode: python ; coding: utf-8 -*-
import re
import sys
from pathlib import Path

block_cipher = None
root = Path(SPECPATH)  # noqa: F821 (injected by PyInstaller)

# Single source of truth: read __version__ from zebra/__init__.py without
# importing the package (avoids pulling Flask etc. into the build process).
_init = (root / 'zebra' / '__init__.py').read_text(encoding='utf-8')
_m = re.search(r"^__version__\s*=\s*['\"]([^'\"]+)['\"]", _init, re.M)
APP_VERSION = _m.group(1) if _m else '0.0.0'

datas = [
    (str(root / 'templates'),      'templates'),
    (str(root / 'static'),         'static'),
    (str(root / 'seed_profiles'),  'seed_profiles'),
]

hiddenimports = [
    # pywebview platform backends — picked at runtime depending on OS.
    'webview',
    'webview.platforms.cocoa',
    'webview.platforms.winforms',
    'webview.platforms.gtk',
    # Zebra app subpackages (collected via Analysis, but listing them here
    # guards against PyInstaller missing dynamically-imported modules).
    'zebra',
    'zebra.routes',
    'zebra.routes.config',
    'zebra.routes.labels',
    'zebra.routes.tmpl',
    'zebra.datasources',
    'zebra.datasources.base',
    'zebra.datasources.mssql',
    'zebra.datasources.registry',
]

# Optional MSSQL deps — include if installed in the build environment so the
# packaged exe can talk to SQL Server. Missing modules are silently skipped.
for opt in ('pymssql', 'pyodbc'):
    try:
        __import__(opt)
        hiddenimports.append(opt)
    except ImportError:
        pass

a = Analysis(  # noqa: F821
    ['desktop.py'],
    pathex=[str(root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=['tkinter'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='DoctorZebra',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # no terminal window on Windows
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(root / 'static' / 'icon.ico') if (root / 'static' / 'icon.ico').is_file() else None,
)

# macOS app bundle
if sys.platform == 'darwin':
    app = BUNDLE(  # noqa: F821
        exe,
        name='DoctorZebra.app',
        icon=str(root / 'static' / 'icon.icns') if (root / 'static' / 'icon.icns').is_file() else None,
        bundle_identifier='com.doctorzebra.app',
        info_plist={
            'CFBundleName': 'Doctor Zebra',
            'CFBundleDisplayName': 'Doctor Zebra',
            'CFBundleShortVersionString': APP_VERSION,
            'NSHighResolutionCapable': True,
            'LSBackgroundOnly': False,
        },
    )
