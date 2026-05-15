"""Browser-mode launcher for Comandante Zebra.

Same embedded Flask server as ``desktop.py``, but instead of opening a
native pywebview window it opens the user's default web browser. This
removes the WebKitGTK / GObject-introspection system dependency that
makes packaging ``desktop.py`` painful on Linux — the binary built from
this entry point is fully self-contained and runs on any desktop (and
on headless/kiosk boxes too).

Used as the entry point for the Linux ``.deb`` / ``.rpm`` / standalone
binary (see ``build_linux.spec`` and ``.github/workflows/build-linux.yml``).
Run directly::

    python desktop_browser.py

Data layout, profile seeding, the legacy ``~/.zebra_labels/`` rename and
mDNS LAN discovery are all inherited unchanged from ``desktop.py`` — we
reuse its helpers so there is a single source of truth for the Flask
bootstrap. Importing ``desktop`` does NOT pull in ``webview`` (that
import is lazy, inside ``desktop.main``), so this stays GTK-free.
"""

from __future__ import annotations

import logging
import sys
import threading
import webbrowser

import desktop  # reuses _resolve_base_dir / _find_free_port / _run_flask / _wait_until_ready


def main() -> int:
    base_dir = desktop._resolve_base_dir()
    port = desktop._find_free_port()
    host = '127.0.0.1'
    url = f'http://{host}:{port}/'

    logging.info(f'Starting embedded Flask (browser mode) on {url} (base_dir={base_dir})')
    t = threading.Thread(
        target=desktop._run_flask,
        args=(host, port, base_dir),
        daemon=True,
    )
    t.start()

    if not desktop._wait_until_ready(url):
        logging.error('Flask did not become ready in time')
        sys.stderr.write('Comandante Zebra: el servidor no arrancó a tiempo.\n')
        return 1

    logging.info('Opening system browser')
    try:
        webbrowser.open(url)
    except Exception as e:  # noqa: BLE001
        logging.warning(f'Could not open browser automatically: {e}')

    print(
        f'Comandante Zebra está corriendo en {url}\n'
        'Si no se abrió el navegador, abre esa dirección manualmente.\n'
        'Cierra esta ventana/terminal (Ctrl+C) para detenerlo.'
    )

    # Flask runs in the daemon thread; block here until it dies or the
    # user interrupts. Closing the controlling terminal / process ends it.
    try:
        while t.is_alive():
            t.join(timeout=1.0)
    except KeyboardInterrupt:
        logging.info('Interrupted by user — shutting down')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
