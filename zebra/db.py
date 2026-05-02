"""SQLite access: connection helper, schema init, and label repository.

Two tables may coexist:

* ``labels`` — legacy schema from before per-template dynamic fields existed.
  Kept read-only for historical visibility.
* ``label_prints`` — current schema. Stores the submitted form values as a
  single ``fields_json`` blob so any set of fields can be recorded.
"""

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

_LEGACY_SCHEMA = '''
CREATE TABLE IF NOT EXISTS labels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    template_file TEXT,
    recipient_name TEXT,
    recipient_address TEXT,
    recipient_city_state TEXT,
    recipient_country TEXT,
    printed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
'''

_SCHEMA = '''
CREATE TABLE IF NOT EXISTS label_prints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    template_file TEXT NOT NULL,
    fields_json TEXT NOT NULL DEFAULT '{}',
    printed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
'''

_LEGACY_COLS = (
    'recipient_name', 'recipient_address',
    'recipient_city_state', 'recipient_country',
)


@contextmanager
def connect(db_path: str | Path) -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(db_path)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(db_path: str | Path) -> None:
    with connect(db_path) as conn:
        conn.execute(_LEGACY_SCHEMA)
        conn.execute(_SCHEMA)


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------

def insert(db_path: str | Path, template_file: str, fields: dict) -> int:
    """Insert a print record. ``fields`` is serialised to JSON."""
    payload = json.dumps(fields or {}, ensure_ascii=False)
    with connect(db_path) as conn:
        cur = conn.execute(
            'INSERT INTO label_prints (template_file, fields_json) VALUES (?, ?)',
            (template_file, payload),
        )
        return cur.lastrowid or 0


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

def most_recent(db_path: str | Path) -> tuple[str, dict] | None:
    """Return ``(template_file, fields_dict)`` for the latest job, or None."""
    with connect(db_path) as conn:
        row = conn.execute(
            'SELECT template_file, fields_json FROM label_prints '
            'ORDER BY printed_at DESC LIMIT 1'
        ).fetchone()
    if row:
        return (row[0], _decode_fields(row[1]))

    # Fall back to legacy table so existing installs still pre-fill.
    return _most_recent_legacy(db_path)


def get_by_id(db_path: str | Path, label_id: int) -> tuple[str, dict] | None:
    """Fetch a specific record. Handles IDs from either table.

    The history view encodes legacy IDs with a ``legacy:`` prefix so we can
    disambiguate; here we accept either form for convenience.
    """
    legacy = False
    try:
        if isinstance(label_id, str) and label_id.startswith('legacy:'):
            legacy = True
            label_id = int(label_id.split(':', 1)[1])
        else:
            label_id = int(label_id)
    except (TypeError, ValueError):
        return None

    with connect(db_path) as conn:
        if not legacy:
            row = conn.execute(
                'SELECT template_file, fields_json FROM label_prints WHERE id=?',
                (label_id,),
            ).fetchone()
            if row:
                return (row[0], _decode_fields(row[1]))
        # Try legacy table as fallback
        row = conn.execute(
            f'SELECT template_file, {", ".join(_LEGACY_COLS)} '
            'FROM labels WHERE id=?',
            (label_id,),
        ).fetchone()
    if not row:
        return None
    return (row[0], _legacy_row_to_fields(row[1:]))


def list_all(db_path: str | Path) -> list[dict]:
    """Return a unified list of print records for the history view.

    Each item is ``{id, template_file, fields, printed_at, source}``.
    """
    out: list[dict] = []
    with connect(db_path) as conn:
        for row in conn.execute(
            'SELECT id, template_file, fields_json, printed_at '
            'FROM label_prints ORDER BY printed_at DESC'
        ):
            out.append({
                'id': row[0],
                'template_file': row[1],
                'fields': _decode_fields(row[2]),
                'printed_at': row[3],
                'source': 'current',
            })

        for row in conn.execute(
            f'SELECT id, template_file, {", ".join(_LEGACY_COLS)}, printed_at '
            'FROM labels ORDER BY printed_at DESC'
        ):
            out.append({
                'id': f'legacy:{row[0]}',
                'template_file': row[1],
                'fields': _legacy_row_to_fields(row[2:6]),
                'printed_at': row[6],
                'source': 'legacy',
            })
    out.sort(key=lambda r: r['printed_at'] or '', reverse=True)
    return out


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _decode_fields(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except (ValueError, TypeError):
        return {}


def _legacy_row_to_fields(values: tuple) -> dict:
    out: dict[str, str] = {}
    for col, val in zip(_LEGACY_COLS, values):
        if val:
            out[col] = val
    return out


def _most_recent_legacy(db_path: str | Path) -> tuple[str, dict] | None:
    with connect(db_path) as conn:
        row = conn.execute(
            f'SELECT template_file, {", ".join(_LEGACY_COLS)} '
            'FROM labels ORDER BY printed_at DESC LIMIT 1'
        ).fetchone()
    if not row:
        return None
    return (row[0], _legacy_row_to_fields(row[1:]))
