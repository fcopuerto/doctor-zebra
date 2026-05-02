"""Native desktop wrapper for Comandante Zebra.

Starts Flask on a random localhost port in a background thread, then opens
a pywebview window pointed at it. Closing the window terminates the process.

Run directly::

    python desktop.py

Packaged with PyInstaller via ``build_desktop.spec``.

Data layout
-----------

When frozen with PyInstaller the bundle contains the read-only app assets
(templates/, static/, the ``zebra`` package, and a ``seed_profiles/``
skeleton).  User-writable state lives in ``~/.comandante_zebra/``:

* ``profiles/<name>/config.cfg`` – per-profile settings (edited from the UI).
* ``profiles/<name>/labels.db``  – per-profile SQLite history.
* ``profiles/<name>/templates_zpl/`` – per-profile ZPL templates.
* ``app.log`` – log file.

On first run, ``seed_profiles/default/`` is copied into
``~/.comandante_zebra/profiles/default/`` so the user starts with a working
profile they can edit. Running from source keeps everything in the project
directory.

Migration: if a legacy ``~/.zebra_labels/`` directory exists from a previous
build, it is renamed to ``~/.comandante_zebra/`` on first launch so user data
follows the rebrand.
"""

from __future__ import annotations

import base64
import json
import locale
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

SUPPORTED_LANGS = ('en', 'es', 'ca')
SPLASH_DEFAULT_LANG = 'es'

FROZEN = bool(getattr(sys, 'frozen', False))
BUNDLE_DIR = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))

USER_DIR = Path.home() / '.comandante_zebra'
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
    ``~/.comandante_zebra/`` so the user's data survives upgrades.
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


# How long the splash holds the screen *at minimum*, even when Flask comes
# up faster. Long enough for the seven loading steps to play out and for
# the brand to register — short enough to not feel like a punishment.
SPLASH_MIN_MS = 6500
SPLASH_STEP_COUNT = 8


def _pick_splash_lang() -> str:
    """Decide which catalog the splash should use.

    Priority:
      1. ``~/.comandante_zebra/lang.txt`` written by /api/lang/<code>. This is
         what the user explicitly chose in a previous session.
      2. The OS primary locale (so a Spanish-locale machine on first run
         already gets a Spanish splash, matching the Flask default).
      3. SPLASH_DEFAULT_LANG.
    """
    try:
        f = USER_DIR / 'lang.txt'
        if f.is_file():
            v = f.read_text(encoding='utf-8').strip().lower()
            if v in SUPPORTED_LANGS:
                return v
    except OSError:
        pass
    try:
        sys_lang = (locale.getdefaultlocale()[0] or '').split('_')[0].lower()
        if sys_lang in SUPPORTED_LANGS:
            return sys_lang
    except Exception:  # noqa: BLE001
        pass
    return SPLASH_DEFAULT_LANG


def _load_catalog(lang: str) -> dict:
    """Read i18n/<lang>.json from the bundle. Falls back to default."""
    for code in (lang, SPLASH_DEFAULT_LANG, 'en'):
        p = BUNDLE_DIR / 'i18n' / f'{code}.json'
        if p.is_file():
            try:
                return json.loads(p.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                continue
    return {}


def _splash_html(version: str) -> str:
    """Return a self-contained HTML page for the splash window.

    Renders instantly: the logo is embedded as base64 inline and the
    loading steps are baked into a tiny inline script. No network, no
    Flask, no external assets needed.
    """
    logo_path = BUNDLE_DIR / 'static' / 'icon.png'
    logo_b64 = ''
    if logo_path.is_file():
        logo_b64 = base64.b64encode(logo_path.read_bytes()).decode('ascii')
    img_tag = (
        f'<img class="splash__logo" src="data:image/png;base64,{logo_b64}" alt="">'
        if logo_b64 else ''
    )

    cat = _load_catalog(_pick_splash_lang())
    tagline = cat.get('splash.tagline', 'ZPL printing, made simple.')
    steps = [cat.get(f'splash.step.{i}', '') for i in range(1, SPLASH_STEP_COUNT + 1)]
    steps = [s for s in steps if s]
    steps_json = json.dumps(steps, ensure_ascii=False)

    # Each step is on screen for roughly the same slice of SPLASH_MIN_MS.
    # Subtract ~400ms head-room so the bar reaches 100% slightly before the
    # window is swapped out — feels intentional rather than abrupt.
    step_interval_ms = max(400, (SPLASH_MIN_MS - 400) // max(1, len(steps)))

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Comandante Zebra</title>
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
    width: 130px; height: 130px; margin-bottom: 18px;
    filter: drop-shadow(0 6px 18px rgba(0, 0, 0, 0.35));
  }}
  .splash__title {{
    font-size: 32px; font-weight: 700; letter-spacing: -0.02em; margin: 0;
  }}
  .splash__tagline {{
    font-size: 13px; color: rgba(255, 255, 255, 0.65);
    margin: 6px 0 26px; letter-spacing: 0.01em;
  }}

  /* Progress bar */
  .splash__progress {{
    width: 280px; height: 4px;
    background: rgba(255, 255, 255, 0.10);
    border-radius: 999px; overflow: hidden;
  }}
  .splash__progress-fill {{
    height: 100%; width: 0%;
    background: linear-gradient(90deg, #38bdf8, #fff);
    border-radius: 999px;
    transition: width 0.45s ease-out;
  }}
  .splash__step {{
    margin-top: 12px; min-height: 16px;
    font-size: 12px; color: rgba(255, 255, 255, 0.75);
    font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace;
    letter-spacing: 0.01em;
    transition: opacity 0.18s ease-in-out;
  }}
  .splash__step.is-fading {{ opacity: 0; }}

  .splash__footer {{
    position: fixed; bottom: 14px; left: 0; right: 0;
    display: flex; justify-content: space-between;
    padding: 0 22px; font-size: 11px; color: rgba(255, 255, 255, 0.45);
    font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace;
  }}
</style>
</head>
<body>
  {img_tag}
  <h1 class="splash__title">Comandante Zebra</h1>
  <p class="splash__tagline">{tagline}</p>

  <div class="splash__progress">
    <div class="splash__progress-fill" id="bar"></div>
  </div>
  <p class="splash__step" id="step">&nbsp;</p>

  <div class="splash__footer">
    <span>v{version}</span>
    <span>comandante_zebra</span>
  </div>

<script>
  (function () {{
    const steps = {steps_json};
    const interval = {step_interval_ms};
    const bar = document.getElementById('bar');
    const step = document.getElementById('step');
    const total = steps.length;
    let i = 0;

    function show(idx) {{
      step.classList.add('is-fading');
      setTimeout(function () {{
        step.textContent = steps[idx];
        step.classList.remove('is-fading');
      }}, 160);
      bar.style.width = ((idx + 1) / total * 100) + '%';
    }}

    if (total > 0) {{
      show(0);
      const iv = setInterval(function () {{
        i++;
        if (i >= total) {{ clearInterval(iv); return; }}
        show(i);
      }}, interval);
    }}
  }})();
</script>
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
        'Comandante Zebra',
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
            'Comandante Zebra',
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
