"""Take screenshots of Comandante Zebra for the README / docs.

Run locally:
    uv run python scripts/take_screenshots.py

Run in CI: see .github/workflows/screenshots.yml

The script assumes the Flask app is already running at BASE_URL.
It writes PNGs to docs/screenshots/.
"""

from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_URL = "http://127.0.0.1:5000"
OUT_DIR = Path("docs/screenshots")
VIEWPORT = {"width": 1440, "height": 900}

# Each entry: (output filename, path on the app, optional setup callback)
#
# 👉 Adjust these paths to match your real Flask routes.
#    Inspect zebra/routes/ to find the actual URLs registered by each blueprint.
#    Pages that need data (filled labels, populated template list) should wait
#    until the demo seed profile lands — keep this list to data-free screens
#    for now (Phase 1).
SHOTS: list[tuple[str, str]] = [
    ("01-home.png", "/"),
    ("02-templates.png", "/templates"),
    ("03-template-editor.png", "/templates/new"),
    ("04-settings.png", "/settings"),
    ("05-network.png", "/settings/network"),
    ("06-wizard.png", "/settings/wizard"),
]

# ---------------------------------------------------------------------------


def take_shot(page: Page, filename: str, path: str) -> None:
    url = f"{BASE_URL}{path}"
    print(f"  → {filename}  ({url})")
    try:
        page.goto(url, wait_until="networkidle", timeout=15_000)
    except Exception as exc:  # pragma: no cover - best effort
        print(f"    ⚠️  navigation failed: {exc}")
        return

    # Give any client-side JS / fonts / theme a beat to settle.
    page.wait_for_timeout(500)

    out_path = OUT_DIR / filename
    page.screenshot(path=str(out_path), full_page=True)
    size_kb = out_path.stat().st_size // 1024
    print(f"    ✓ saved ({size_kb} KB)")


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(
            viewport=VIEWPORT,
            device_scale_factor=2,   # retina-quality PNGs
            color_scheme="light",
        )
        page = context.new_page()

        # Surface JS errors so a broken page doesn't silently produce a blank shot.
        page.on("pageerror", lambda e: print(f"    [pageerror] {e}"))
        page.on(
            "console",
            lambda msg: msg.type == "error" and print(f"    [console.error] {msg.text}"),
        )

        for filename, path in SHOTS:
            take_shot(page, filename, path)

        browser.close()

    print(f"\nDone. {len(SHOTS)} shots in {OUT_DIR}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())