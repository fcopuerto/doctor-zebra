"""Native desktop wrapper for Doctor Zebra.

Starts Flask on a random localhost port in a background thread, then opens
a pywebview window pointed at it. Closing the window terminates the process.

Run directly::

    python desktop.py

Packaged with PyInstaller via ``build_desktop.spec``.

Data layout
-----------

When frozen with PyInstaller the bundle contains the read-only app assets
(templates/, static/, the ``zebra`` package, and a ``seed_profiles/``
skeleton).  User-writable state lives in ``~/.doctor_zebra/``:

* ``profiles/<name>/config.cfg`` – per-profile settings (edited from the UI).
* ``profiles/<name>/labels.db``  – per-profile SQLite history.
* ``profiles/<name>/templates_zpl/`` – per-profile ZPL templates.
* ``app.log`` – log file.

On first run, ``seed_profiles/default/`` is copied into
``~/.doctor_zebra/profiles/default/`` so the user starts with a working
profile they can edit. Running from source keeps everything in the project
directory.

Migration: if a legacy ``~/.zebra_labels/`` directory exists from a previous
build, it is renamed to ``~/.doctor_zebra/`` on first launch so user data
follows the rebrand.
"""

from __future__ import annotations

import logging
import os
import shutil
import socket
import sys
import threading
import time
from pathlib import Path
from urllib.request import urlopen
from urllib.error import URLError

FROZEN = bool(getattr(sys, 'frozen', False))
BUNDLE_DIR = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))

USER_DIR = Path.home() / '.doctor_zebra'
_LEGACY_DIR = Path.home() / '.zebra_labels'
if _LEGACY_DIR.is_dir() and not USER_DIR.exists():
    # One-shot rename of the pre-rebrand data dir.
    _LEGACY_DIR.rename(USER_DIR)
USER_DIR.mkdir(parents=True, exist_ok=True)

LOG_PATH = USER_DIR / 'app.log' if FROZEN else Path('zebra_app.log')
logging.basicConfig(
    filename=LOG_PATH,
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
)


def _resolve_base_dir() -> Path:
    """Return the writable base dir that holds ``profiles/``.

    When running from source, that's the project root (so editing profiles
    from the UI updates the working tree). When frozen, it's
    ``~/.doctor_zebra/`` so the user's data survives upgrades.
    """
    if not FROZEN:
        return Path(__file__).resolve().parent

    # First-run seeding: copy bundled seed_profiles/default/ → user profiles/.
    user_profiles = USER_DIR / 'profiles'
    seed_default = BUNDLE_DIR / 'seed_profiles' / 'default'
    user_default = user_profiles / 'default'
    if not user_default.is_dir() and seed_default.is_dir():
        user_profiles.mkdir(parents=True, exist_ok=True)
        shutil.copytree(seed_default, user_default)
        logging.info(f'Seeded default profile at {user_default}')

    return USER_DIR


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def _wait_until_ready(url: str, timeout: float = 8.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urlopen(url, timeout=0.5) as resp:
                if resp.status < 500:
                    return True
        except URLError:
            time.sleep(0.1)
    return False


def _run_flask(host: str, port: int, base_dir: Path) -> None:
    # Import late so the logging config above is already in effect
    from zebra import create_app

    app = create_app(base_dir=base_dir)
    app.run(host=host, port=port, debug=False, use_reloader=False, threaded=True)


def main() -> int:
    try:
        import webview  # type: ignore
    except ImportError:
        sys.stderr.write(
            'pywebview is not installed. Run: pip install pywebview\n'
        )
        return 1

    base_dir = _resolve_base_dir()

    port = _find_free_port()
    host = '127.0.0.1'
    url = f'http://{host}:{port}/'

    logging.info(f'Starting embedded Flask on {url} (base_dir={base_dir})')
    t = threading.Thread(
        target=_run_flask,
        args=(host, port, base_dir),
        daemon=True,
    )
    t.start()

    if not _wait_until_ready(url):
        logging.error('Flask did not become ready in time')
        sys.stderr.write('Flask failed to start\n')
        return 2

    webview.create_window(
        'Doctor Zebra',
        url,
        width=1200,
        height=820,
        min_size=(900, 600),
        confirm_close=False,
    )
    webview.start()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
