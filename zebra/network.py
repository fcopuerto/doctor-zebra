"""Network identity for Comandante Zebra: peer name, share PIN, prefs.

Persisted to ``<base_dir>/network.json`` so it survives restarts and is
the same source the discovery announcement, the /api/network/me endpoint
and the /api/peer/* PIN check all read.

Schema::

    {
        "peer_name":          "fran-mac",
        "pin":                "147823",
        "share_templates":    true,
        "share_connections":  false
    }

The PIN is a 6-digit numeric string. It is **never** broadcast on mDNS
(only the peer name + version + profile are). To pull anything from a
peer the calling client must include the right PIN as a query param.
"""

from __future__ import annotations

import json
import logging
import secrets
import socket
from pathlib import Path
from threading import Lock

NETWORK_FILE = 'network.json'

DEFAULTS = {
    'peer_name':         '',     # filled in on first boot from socket.gethostname()
    'pin':               '',     # generated on first boot
    'share_templates':   True,
    'share_connections': False,
}

# Single in-process state — Flask reads/writes this dict from multiple
# request threads, so guard with a lock. The file write is also done
# under the lock so the JSON on disk never gets a half-update.
_LOCK = Lock()
_STATE: dict = dict(DEFAULTS)
_BASE_DIR: Path | None = None


def _file() -> Path:
    if _BASE_DIR is None:
        raise RuntimeError('network.init() not called yet')
    return Path(_BASE_DIR) / NETWORK_FILE


def init(base_dir: Path) -> dict:
    """Load or create network.json. Call once at app startup."""
    global _BASE_DIR, _STATE
    _BASE_DIR = Path(base_dir)
    Path(_BASE_DIR).mkdir(parents=True, exist_ok=True)

    f = _file()
    loaded: dict = {}
    if f.is_file():
        try:
            data = json.loads(f.read_text(encoding='utf-8'))
            if isinstance(data, dict):
                loaded = data
        except (OSError, ValueError) as e:
            logging.warning(f'Bad network.json, regenerating: {e}')

    state = {**DEFAULTS, **loaded}
    if not state.get('peer_name'):
        state['peer_name'] = socket.gethostname() or 'comandante-zebra'
    if not state.get('pin') or not _is_valid_pin(state.get('pin', '')):
        state['pin'] = _gen_pin()
    state['share_templates']   = bool(state.get('share_templates', True))
    state['share_connections'] = bool(state.get('share_connections', False))

    with _LOCK:
        _STATE = state
        try:
            f.write_text(json.dumps(state, indent=2) + '\n', encoding='utf-8')
        except OSError as e:
            logging.warning(f'Could not persist network.json: {e}')
    logging.info(
        f'Network identity: name={state["peer_name"]} '
        f'share_templates={state["share_templates"]} '
        f'share_connections={state["share_connections"]}'
    )
    return dict(state)


def _gen_pin() -> str:
    # 6 digits, leading zeroes preserved, drawn from a CSPRNG.
    return f'{secrets.randbelow(1_000_000):06d}'


def _is_valid_pin(s: str) -> bool:
    return isinstance(s, str) and len(s) == 6 and s.isdigit()


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

def snapshot() -> dict:
    """Return a copy of the current state (safe to mutate by caller)."""
    with _LOCK:
        return dict(_STATE)


def pin() -> str:
    return snapshot().get('pin', '')


def peer_name() -> str:
    return snapshot().get('peer_name', '')


def shares_templates() -> bool:
    return bool(snapshot().get('share_templates', True))


def shares_connections() -> bool:
    return bool(snapshot().get('share_connections', False))


def check_pin(candidate: str | None) -> bool:
    """Constant-time-ish comparison against the configured PIN."""
    real = pin()
    if not candidate or not real or len(candidate) != len(real):
        return False
    return secrets.compare_digest(candidate, real)


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------

def update(patch: dict) -> dict:
    """Merge ``patch`` into the state, validate, persist, return snapshot."""
    global _STATE
    with _LOCK:
        new = dict(_STATE)
        if 'peer_name' in patch:
            n = str(patch['peer_name'] or '').strip()
            if n:
                # Keep it short and printable; mDNS instance names are
                # length-limited and browsers truncate ugly strings.
                new['peer_name'] = n[:48]
        if 'share_templates' in patch:
            new['share_templates'] = bool(patch['share_templates'])
        if 'share_connections' in patch:
            new['share_connections'] = bool(patch['share_connections'])
        if 'pin' in patch:
            v = str(patch['pin'] or '').strip()
            if _is_valid_pin(v):
                new['pin'] = v
        _STATE = new
        try:
            _file().write_text(json.dumps(new, indent=2) + '\n', encoding='utf-8')
        except OSError as e:
            logging.warning(f'Could not persist network.json: {e}')
        return dict(new)


def regenerate_pin() -> str:
    """Roll a new PIN. Returns the new value."""
    with _LOCK:
        _STATE['pin'] = _gen_pin()
        try:
            _file().write_text(json.dumps(_STATE, indent=2) + '\n', encoding='utf-8')
        except OSError as e:
            logging.warning(f'Could not persist network.json: {e}')
        return _STATE['pin']
