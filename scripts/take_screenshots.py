"""Take screenshots of Comandante Zebra for the README / docs.

Auto-discovers routes by hitting /_routes (only available when the
ZEBRA_DEV_ROUTES env var is set, see zebra/routes/_dev.py).

No hardcoded URL list to maintain — when you add a new page to the app,
the next CI run picks it up automatically.
"""

from __future__ import annotations

import json
import re
import sys
import urllib.request
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_URL = "http://127.0.0.1:5000"
OUT_DIR = Path("docs/screenshots")
VIEWPORT = {"width": 1440, "height": 900}

# Routes we never want to screenshot, even if /_routes returns them.
# Add any internal/API/JSON-only endpoints here.
SKIP_PATTERNS = [
    r"^/api(/|$)",
    r"^/healthz?$",
    r"\.json$",
    r"\.zpl$",
    r"^/print(/|$)",          # printing endpoints — not visual
    r"^/download(/|$)",
    r"^/export(/|$)",
]

SKIP_RE = re.compile("|".join(SKIP_PATTERNS))

# ---------------------------------------------------------------------------


def discover_routes() -> list[str]:
    """Fetch the route list from the running app's /_routes endpoint."""
    url = f"{BASE_URL}/_routes"
    print(f"Discovering routes from {url} ...")
    with urllib.request.urlopen(url, timeout=10) as resp:
        data = json.loads(resp.read())

    routes = []
    for entry in data:
        rule = entry["rule"]
        if SKIP_RE.search(rule):
            print(f"  · skip {rule}")
            continue
        routes.append(rule)

    print(f"  {len(routes)} route(s) selected for screenshots.")
    return routes


def slug_for(rule: str) -> str:
    """Turn /settings/network into 'settings-network'."""
    if rule == "/":
        return "home"
    return rule.strip("/").replace("/", "-") or "root"


def take_shot(page: Page, index: int, rule: str) -> bool:
    filename = f"{index:02d}-{slug_for(rule)}.png"
    url = f"{BASE_URL}{rule}"
    print(f"  → {filename}  ({url})")
    try:
        response = page.goto(url, wait_until="networkidle", timeout=15_000)
    except Exception as exc:
        print(f"    ⚠️  navigation failed: {exc}")
        return False

    status = response.status if response else 0
    if status >= 400:
        print(f"    ⚠️  HTTP {status} — skipping")
        return False

    page.wait_for_timeout(500)  # let fonts/JS settle
    out_path = OUT_DIR / filename
    page.screenshot(path=str(out_path), full_page=True)
    size_kb = out_path.stat().st_size // 1024
    print(f"    ✓ saved ({size_kb} KB)")
    return True


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Wipe stale screenshots so removed pages don't linger in docs/.
    for old in OUT_DIR.glob("*.png"):
        old.unlink()

    try:
        routes = discover_routes()
    except Exception as exc:
        print(f"❌ Could not reach /_routes: {exc}")
        print("   Make sure the app is running and ZEBRA_DEV_ROUTES=1.")
        return 1

    if not routes:
        print("❌ No routes returned. Nothing to screenshot.")
        return 1

    saved = 0
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(
            viewport=VIEWPORT,
            device_scale_factor=2,   # retina-quality PNGs
            color_scheme="light",
        )
        page = context.new_page()

        page.on("pageerror", lambda e: print(f"    [pageerror] {e}"))
        page.on(
            "console",
            lambda msg: msg.type == "error" and print(f"    [console.error] {msg.text}"),
        )

        for i, rule in enumerate(routes, start=1):
            if take_shot(page, i, rule):
                saved += 1

        browser.close()

    print(f"\nDone. {saved}/{len(routes)} shots saved to {OUT_DIR}/")
    return 0 if saved else 1


if __name__ == "__main__":
    sys.exit(main())
