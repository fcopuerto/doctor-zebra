# PyInstaller spec for the Linux browser-mode build of Comandante Zebra.
#
# Build (on Linux):
#   uv sync --extra mssql-pure --group build
#   uv run pyinstaller --noconfirm --clean build_linux.spec
#
# Output: dist/ComandanteZebra  (single-file ELF, no extension)
#
# Why a separate spec from build_desktop.spec
# -------------------------------------------
# build_desktop.spec freezes desktop.py (pywebview / native window), which
# on Linux drags in WebKitGTK + GObject-introspection — system libraries
# PyInstaller can't bundle reliably across distros. This spec freezes
# desktop_browser.py instead, which opens the system browser and never
# imports `webview`, so the binary is self-contained and distro-agnostic.
# It is the artifact wrapped by the .deb / .rpm (see packaging/nfpm.yaml).
#
# Layout when frozen matches build_desktop.spec: read-only assets
# (templates/, static/, i18n/, seed_profiles/) ship in the bundle; user
# state lives in ~/.comandante_zebra/ (see desktop.py).

# -*- mode: python ; coding: utf-8 -*-
import re
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
    (str(root / 'i18n'),           'i18n'),
    (str(root / 'seed_profiles'),  'seed_profiles'),
]

# No `webview.*` here on purpose: browser mode never imports pywebview,
# so we keep the binary GTK-free and smaller.
hiddenimports = [
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

# Optional MSSQL deps — include if installed in the build environment so
# the packaged binary can talk to SQL Server. Missing modules are skipped.
for opt in ('pymssql', 'pyodbc'):
    try:
        __import__(opt)
        hiddenimports.append(opt)
    except ImportError:
        pass

a = Analysis(  # noqa: F821
    ['desktop_browser.py'],
    pathex=[str(root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=['tkinter', 'webview'],
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
    name='ComandanteZebra',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    # Keep stdio: this build prints the local URL and logs to the
    # terminal when launched from one; harmless when launched via the
    # .desktop entry (no terminal is spawned on Linux).
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
