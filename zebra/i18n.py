"""Lightweight JSON-based translations.

Why not Flask-Babel: this app has a few hundred strings and ships as a
single .exe. A flat ``i18n/<lang>.json`` per language is enough, doesn't
require ``pybabel extract``/``compile`` steps, and the bundle stays
trivial to package.

Public API:

* :func:`load_all` — read every JSON in the i18n directory once at
  startup.
* :func:`available` — list of ``{code, name}`` for the language selector.
* :func:`translate` — resolve a key for a given language; falls back to
  English then to the key itself so missing translations are visible
  without breaking the UI.
* :func:`pick` — choose the best language code from a request's cookie
  and ``Accept-Language`` header.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

# Default fallback chain. English is the source-of-truth catalogue —
# every other language inherits any missing key from it.
DEFAULT_LANG = 'es'
FALLBACK_LANG = 'en'

# Loaded once and treated as read-only.
_CATALOGS: dict[str, dict[str, str]] = {}


def load_all(i18n_dir: Path) -> dict[str, dict[str, str]]:
    """Read every ``<lang>.json`` from ``i18n_dir`` into the cache."""
    _CATALOGS.clear()
    if not i18n_dir.is_dir():
        logging.warning(f'i18n directory not found: {i18n_dir}')
        return _CATALOGS
    for p in sorted(i18n_dir.glob('*.json')):
        try:
            data = json.loads(p.read_text(encoding='utf-8'))
            if isinstance(data, dict):
                _CATALOGS[p.stem.lower()] = {str(k): str(v) for k, v in data.items()}
        except (OSError, ValueError) as e:
            logging.warning(f'Failed to load i18n catalog {p}: {e}')
    return _CATALOGS


def available() -> list[dict]:
    """Return ``[{code, name}, ...]`` for the language selector."""
    out: list[dict] = []
    for code, cat in _CATALOGS.items():
        out.append({
            'code': code,
            'name': cat.get('lang.name', code),
            'short': cat.get('lang.code', code.upper()),
        })
    out.sort(key=lambda c: c['code'])
    return out


def is_supported(code: str | None) -> bool:
    return bool(code) and code.lower() in _CATALOGS


def translate(key: str, lang: str | None) -> str:
    """Resolve ``key`` in ``lang`` with English fallback then key passthrough."""
    if not key:
        return ''
    code = (lang or '').lower()
    cat = _CATALOGS.get(code)
    if cat and key in cat:
        return cat[key]
    fb = _CATALOGS.get(FALLBACK_LANG)
    if fb and key in fb:
        return fb[key]
    # Last resort: return the key itself so missing translations are
    # visible during development without crashing the page.
    return key


# ---------------------------------------------------------------------------
# Language selection from a request
# ---------------------------------------------------------------------------

# Regex over a subset of RFC 7231 Accept-Language. We only care about the
# primary tag (en-US → en, es-419 → es, ca → ca) and ignore q-values.
_ACCEPT_LANG_TAG = re.compile(r'([a-zA-Z]{2,3})')


def _from_accept_language(header: str | None) -> str | None:
    if not header:
        return None
    for chunk in header.split(','):
        m = _ACCEPT_LANG_TAG.match(chunk.strip())
        if m and is_supported(m.group(1).lower()):
            return m.group(1).lower()
    return None


def pick(cookie: str | None, accept_language: str | None) -> str:
    """Choose the best language: cookie → Accept-Language → DEFAULT_LANG."""
    if is_supported(cookie):
        return cookie.lower()  # type: ignore[union-attr]
    accepted = _from_accept_language(accept_language)
    if accepted:
        return accepted
    if is_supported(DEFAULT_LANG):
        return DEFAULT_LANG
    return FALLBACK_LANG
