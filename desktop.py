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

import base64
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


# Minimum time the splash stays visible even when Flask is already up — long
# enough to register as a brand moment, short enough to not feel sluggish.
SPLASH_MIN_MS = 1500


def _splash_html(version: str) -> str:
    """Return a self-contained HTML page for the splash window.

    The logo is embedded as base64 so the splash needs no network or local
    web server to render — it shows the instant the window appears.
    """
    logo_path = BUNDLE_DIR / 'static' / 'icon.png'
    logo_b64 = ''
    if logo_path.is_file():
        logo_b64 = base64.b64encode(logo_path.read_bytes()).decode('ascii')

    img_tag = (
        f'<img class="splash__logo" src="data:image/png;base64,{logo_b64}" alt="">'
        if logo_b64 else ''
    )

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Doctor Zebra</title>
<style>
  html, body {{ margin: 0; padding: 0; height: 100vh; overflow: hidden; }}
  body {{
    background: linear-gradient(135deg, #0d1b2a 0%, #1d3557 100%);
    color: #fff;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Helvetica Neue", sans-serif;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    text-align: center;
    user-select: none;
  }}
  .splash__logo {{
    width: 140px; height: 140px; margin-bottom: 22px;
    filter: drop-shadow(0 6px 18px rgba(0, 0, 0, 0.35));
  }}
  .splash__title {{
    font-size: 34px; font-weight: 700; letter-spacing: -0.02em; margin: 0;
  }}
  .splash__tagline {{
    font-size: 13px; color: rgba(255, 255, 255, 0.65); margin: 6px 0 0;
    letter-spacing: 0.01em;
  }}
  .splash__footer {{
    position: fixed; bottom: 14px; left: 0; right: 0;
    display: flex; justify-content: space-between;
    padding: 0 22px; font-size: 11px; color: rgba(255, 255, 255, 0.5);
    font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace;
  }}
  @keyframes pulse {{
    0%, 100% {{ opacity: 0.35; }}
    50%      {{ opacity: 1.0;  }}
  }}
  .splash__loading {{ animation: pulse 1.4s ease-in-out infinite; }}
</style>
</head>
<body>
  {img_tag}
  <h1 class="splash__title">Doctor Zebra</h1>
  <p class="splash__tagline">ZPL printing, made simple.</p>
  <div class="splash__footer">
    <span>v{version}</span>
    <span class="splash__loading">loading…</span>
  </div>
</body></html>
"""


def main() -> int:
    try:
        import webview  # type: ignore
    except ImportError:
        sys.stderr.write(
            'pywebview is not installed. Run: pip install pywebview\n'
        )
        return 1

    # Late import so logging is already configured.
    from zebra import __version__ as app_version

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
    splash_started_at = time.monotonic()

    # Splash window: small, frameless, on top. Replaced by the real app
    # window once Flask is ready (and after a minimum on-screen time).
    splash = webview.create_window(
        'Doctor Zebra',
        html=_splash_html(app_version),
        width=480,
        height=320,
        resizable=False,
        frameless=True,
        on_top=True,
    )

    def _swap_to_main_window():
        ready = _wait_until_ready(url)
        if not ready:
            logging.error('Flask did not become ready in time')
            try:
                splash.destroy()
            except Exception:  # noqa: BLE001
                pass
            return

        # Hold the splash for at least SPLASH_MIN_MS so it actually registers.
        elapsed_ms = (time.monotonic() - splash_started_at) * 1000
        remaining_ms = SPLASH_MIN_MS - elapsed_ms
        if remaining_ms > 0:
            time.sleep(remaining_ms / 1000.0)

        # Open the real app window first, then close the splash. Doing it in
        # this order avoids a flash of empty desktop on platforms that quit
        # the GUI loop when the last window dies.
        webview.create_window(
            'Doctor Zebra',
            url,
            width=1200,
            height=820,
            min_size=(900, 600),
            confirm_close=False,
        )
        try:
            splash.destroy()
        except Exception as e:  # noqa: BLE001
            logging.warning(f'Could not destroy splash window: {e}')

    webview.start(_swap_to_main_window)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
