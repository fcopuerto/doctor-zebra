"""Check GitHub Releases for a newer version of Comandante Zebra.

This is the *passive* half of an updater: we look at the latest tag on
GitHub and tell the UI whether the running version is behind. We do NOT
download, replace or relaunch the binary — that's a separate problem
with significant Windows file-locking gotchas (see F2 in the project
notes). The user clicks "Download" and grabs the .exe themselves.

State lives in ``<base_dir>/update.json``::

    {
        "last_check_utc":  "2026-05-04T10:12:00Z",
        "latest_seen":     "0.8.0",
        "latest_url":      "https://github.com/.../releases/tag/v0.8.0",
        "latest_notes":    "...",
        "latest_published": "2026-05-04T09:00:00Z",
        "dismissed":       "0.8.0"
    }

The cache TTL avoids hammering api.github.com (which rate-limits
unauthenticated callers to 60 req/h per IP — easily blown if multiple
desktop instances on the same NAT poll on every page load).
"""

from __future__ import annotations

import json
import logging
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

REPO = 'fcopuerto/comandante_zebra'
RELEASES_API = f'https://api.github.com/repos/{REPO}/releases/latest'
RELEASES_HTML = f'https://github.com/{REPO}/releases/latest'
STATE_FILE = 'update.json'

# Don't poll GitHub more often than this. 24h is the sweet spot for a
# desktop app: catches releases the next day at most, costs ~zero quota.
CACHE_TTL_SECONDS = 24 * 60 * 60

# Hard timeout on the HTTP call so the UI never hangs waiting for
# api.github.com when the user's offline.
HTTP_TIMEOUT = 4.0

_LOCK = Lock()
_BASE_DIR: Path | None = None


def init(base_dir: Path) -> None:
    """Wire the module to the writable base dir. Call once at startup."""
    global _BASE_DIR
    _BASE_DIR = Path(base_dir)


def _state_path() -> Path | None:
    if _BASE_DIR is None:
        return None
    return _BASE_DIR / STATE_FILE


def _load_state() -> dict:
    p = _state_path()
    if p is None or not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def _save_state(state: dict) -> None:
    p = _state_path()
    if p is None:
        return
    try:
        p.write_text(json.dumps(state, indent=2) + '\n', encoding='utf-8')
    except OSError as e:
        logging.warning(f'Could not persist update.json: {e}')


# ---------------------------------------------------------------------------
# SemVer comparison (just enough for our tagging convention)
# ---------------------------------------------------------------------------
#
# Tags look like "v0.7.5" or "0.7.5". We strip the leading 'v', split on
# dots, and compare the integer tuple. Pre-release tags like "0.8.0-rc1"
# fall back to plain string compare for the suffix — close enough for
# Comandante Zebra, where we don't ship pre-releases.

_VERSION_RE = re.compile(r'^v?(\d+)\.(\d+)\.(\d+)(?:[-+](.+))?$')


def _parse(v: str) -> tuple | None:
    m = _VERSION_RE.match((v or '').strip())
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4) or '')


def is_newer(latest: str, current: str) -> bool:
    a, b = _parse(latest), _parse(current)
    if a is None or b is None:
        return False
    # Numeric tuple wins; if equal, an empty pre-release (release) beats
    # a non-empty one (rc/alpha) — in semver that's the "official"
    # version being newer.
    if a[:3] != b[:3]:
        return a[:3] > b[:3]
    if a[3] == b[3]:
        return False
    if not a[3]:
        return True       # release > pre-release of same x.y.z
    if not b[3]:
        return False
    return a[3] > b[3]


# ---------------------------------------------------------------------------
# GitHub fetch
# ---------------------------------------------------------------------------

def _fetch_latest_release() -> dict | None:
    """Return the GitHub release JSON, or None on any failure."""
    req = urllib.request.Request(
        RELEASES_API,
        headers={
            'Accept':     'application/vnd.github+json',
            'User-Agent': 'comandante-zebra-updater',
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            if resp.status != 200:
                return None
            return json.loads(resp.read().decode('utf-8', errors='replace'))
    except Exception as e:  # noqa: BLE001
        logging.info(f'Update check failed (offline?): {e}')
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def check(current_version: str, force: bool = False) -> dict:
    """Return the current update status.

    Result schema::

        {
            "current":         "0.7.5",
            "latest":          "0.8.0" | None,
            "latest_url":      "...",
            "latest_notes":    "...",
            "latest_published":"2026-05-04T09:00:00Z",
            "update_available": true,
            "dismissed":       false,
            "checked_at":      "...",
            "from_cache":      true|false
        }
    """
    with _LOCK:
        state = _load_state()
        last_check = state.get('last_check_utc')

        # Force refresh whenever our own version moved since the last
        # check — otherwise an outdated cache that said "0.13 is
        # available" keeps shouting at users who just installed 0.13.
        version_changed = (
            state.get('current_when_checked')
            and state['current_when_checked'] != current_version
        )

        cached = (
            not force
            and not version_changed
            and last_check
            and _seconds_since(last_check) < CACHE_TTL_SECONDS
            and state.get('latest_seen')
        )
        if not cached:
            data = _fetch_latest_release()
            if data is not None:
                state['latest_seen']         = (data.get('tag_name') or '').lstrip('v')
                state['latest_url']          = data.get('html_url') or RELEASES_HTML
                state['latest_notes']        = data.get('body') or ''
                state['latest_published']    = data.get('published_at') or ''
                state['last_check_utc']      = _utcnow_iso()
                state['current_when_checked'] = current_version
                _save_state(state)
            elif not last_check:
                # First-ever check failed; remember so we don't retry every
                # request. We'll try again after the TTL.
                state['last_check_utc'] = _utcnow_iso()
                _save_state(state)

        latest = state.get('latest_seen') or ''
        update_available = bool(latest) and is_newer(latest, current_version)
        dismissed = (state.get('dismissed') or '') == latest

        return {
            'current':         current_version,
            'latest':          latest or None,
            'latest_url':      state.get('latest_url') or RELEASES_HTML,
            'latest_notes':    state.get('latest_notes') or '',
            'latest_published': state.get('latest_published') or '',
            'update_available': update_available and not dismissed,
            'dismissed':       dismissed,
            'checked_at':      state.get('last_check_utc') or '',
            'from_cache':      cached,
        }


def dismiss(version: str) -> dict:
    """Suppress the update banner for ``version`` until a newer one appears."""
    with _LOCK:
        state = _load_state()
        state['dismissed'] = (version or '').lstrip('v')
        _save_state(state)
        return state


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def _seconds_since(iso: str) -> float:
    try:
        # Tolerate either trailing Z or +00:00.
        s = iso.rstrip('Z')
        ts = datetime.fromisoformat(s).replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - ts).total_seconds()
    except (TypeError, ValueError):
        return float('inf')
