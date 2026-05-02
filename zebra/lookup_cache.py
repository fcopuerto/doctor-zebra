"""Offline cache for database lookups.

Lookup fields always read from this local SQLite cache so the print form
keeps working when the SQL Server is unreachable. The cache is refreshed
manually from the UI by triggering a sync against the live data source.

Schema (in the same SQLite file as the label history):

* ``lookup_cache_meta`` — one row per (connection, table) with the last
  sync timestamp, row count and the column list captured at sync time.
* ``lookup_cache_rows`` — one row per cached row, the data is stored as
  a JSON object keyed by column name. Indexed by (connection, table,
  row_index) — there is no natural primary key on the source side.

Search runs in Python over the cached rows: a case-insensitive substring
match against the configured ``search_columns`` (matches LIKE %q%
behaviour). Latency is O(n) over the cached rows; for the volumes Zebra
labels deal with (tens of thousands at most) it's fine.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from zebra.datasources.base import DataSource


_SCHEMA_META = '''
CREATE TABLE IF NOT EXISTS lookup_cache_meta (
    connection   TEXT NOT NULL,
    table_name   TEXT NOT NULL,
    last_sync    TEXT NOT NULL,
    row_count    INTEGER NOT NULL,
    columns_json TEXT NOT NULL DEFAULT '[]',
    PRIMARY KEY (connection, table_name)
)
'''

_SCHEMA_ROWS = '''
CREATE TABLE IF NOT EXISTS lookup_cache_rows (
    connection TEXT NOT NULL,
    table_name TEXT NOT NULL,
    row_index  INTEGER NOT NULL,
    row_json   TEXT NOT NULL,
    PRIMARY KEY (connection, table_name, row_index)
)
'''

_INDEX_ROWS = (
    'CREATE INDEX IF NOT EXISTS idx_lookup_cache_rows_lookup '
    'ON lookup_cache_rows (connection, table_name, row_index)'
)


def init_cache(db_path: str | Path) -> None:
    """Create the cache tables if missing. Idempotent."""
    with sqlite3.connect(db_path) as conn:
        conn.execute(_SCHEMA_META)
        conn.execute(_SCHEMA_ROWS)
        conn.execute(_INDEX_ROWS)
        conn.commit()


# ---------------------------------------------------------------------------
# Sync
# ---------------------------------------------------------------------------

def sync_table(db_path: str | Path, ds: DataSource, table: str) -> dict:
    """Pull every row from ``table`` and replace the cache for that pair.

    Returns a dict ``{row_count, last_sync, columns}`` describing what was
    written.  Raises whatever the data source raises on failure (caller
    handles).
    """
    rows = ds.fetch_all(table)
    if rows:
        columns = list(rows[0].keys())
    else:
        columns = ds.list_columns(table)

    now = datetime.now(timezone.utc).isoformat(timespec='seconds')

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            'DELETE FROM lookup_cache_rows WHERE connection=? AND table_name=?',
            (ds.name, table),
        )
        if rows:
            conn.executemany(
                'INSERT INTO lookup_cache_rows '
                '(connection, table_name, row_index, row_json) '
                'VALUES (?, ?, ?, ?)',
                [
                    (
                        ds.name, table, i,
                        json.dumps(row, default=_json_default, ensure_ascii=False),
                    )
                    for i, row in enumerate(rows)
                ],
            )
        conn.execute(
            'INSERT OR REPLACE INTO lookup_cache_meta '
            '(connection, table_name, last_sync, row_count, columns_json) '
            'VALUES (?, ?, ?, ?, ?)',
            (ds.name, table, now, len(rows), json.dumps(columns, ensure_ascii=False)),
        )
        conn.commit()

    logging.info(f'Cache sync: {ds.name}/{table} -> {len(rows)} rows')
    return {'row_count': len(rows), 'last_sync': now, 'columns': columns}


def clear(db_path: str | Path, connection: str, table: str) -> bool:
    """Drop cached rows + meta for one (connection, table). Returns whether any meta existed."""
    with sqlite3.connect(db_path) as conn:
        cur = conn.execute(
            'DELETE FROM lookup_cache_meta WHERE connection=? AND table_name=?',
            (connection, table),
        )
        conn.execute(
            'DELETE FROM lookup_cache_rows WHERE connection=? AND table_name=?',
            (connection, table),
        )
        conn.commit()
        return cur.rowcount > 0


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

def get_meta(db_path: str | Path, connection: str, table: str) -> dict | None:
    """Return ``{last_sync, row_count, columns}`` for a cached pair, or None."""
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            'SELECT last_sync, row_count, columns_json FROM lookup_cache_meta '
            'WHERE connection=? AND table_name=?',
            (connection, table),
        ).fetchone()
    if not row:
        return None
    return {
        'last_sync': row[0],
        'row_count': row[1],
        'columns': _decode_json_list(row[2]),
    }


def search(
    db_path: str | Path,
    connection: str,
    table: str,
    search_columns: list[str],
    query: str,
    return_columns: list[str] | None = None,
    limit: int = 25,
) -> list[dict[str, Any]]:
    """Filter cached rows over ``search_columns``.

    Match semantics — case-insensitive, with optional ``*`` wildcards:

    * ``pepe``    → begins-with (the default; equivalent to ``pepe*``)
    * ``pepe*``   → begins-with
    * ``*pepe``   → ends-with
    * ``*pepe*``  → contains
    * ``pe*pe``   → starts with ``pe`` and ends with ``pe``

    The literal characters between ``*`` segments must appear in order
    inside the column value. ``*`` is the only special character — the
    rest are matched verbatim.
    """
    if not search_columns or not query:
        return []
    matcher = _build_matcher(query)
    if matcher is None:
        return []

    out: list[dict] = []
    with sqlite3.connect(db_path) as conn:
        cursor = conn.execute(
            'SELECT row_json FROM lookup_cache_rows '
            'WHERE connection=? AND table_name=? '
            'ORDER BY row_index',
            (connection, table),
        )
        for (row_json,) in cursor:
            try:
                row = json.loads(row_json)
            except (ValueError, TypeError):
                continue
            for col in search_columns:
                v = row.get(col)
                if v is None:
                    continue
                if matcher(str(v).lower()):
                    if return_columns:
                        out.append({c: row.get(c) for c in return_columns})
                    else:
                        out.append(row)
                    break
            if len(out) >= limit:
                break
    return out


def _build_matcher(query: str) -> Callable[[str], bool] | None:
    """Build a value-matcher from a user query.

    Returns None when the query is empty or only made of asterisks.
    """
    q = (query or '').strip().lower()
    if not q or q.replace('*', '') == '':
        return None

    # Default behaviour: begins-with. Only attach the trailing star so the
    # explicit forms (``pepe*``, ``*pepe``, ``pe*pe`` …) still mean what the
    # user typed.
    if '*' not in q:
        q = q + '*'

    pattern = re.escape(q).replace(r'\*', '.*')
    rx = re.compile('^' + pattern + '$')
    return lambda v: rx.match(v) is not None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _json_default(obj):
    """Make non-JSON-native types (Decimal, datetime, bytes…) survive."""
    if hasattr(obj, 'isoformat'):
        return obj.isoformat()
    if isinstance(obj, (bytes, bytearray)):
        try:
            return obj.decode('utf-8', errors='replace')
        except Exception:
            return repr(obj)
    return str(obj)


def _decode_json_list(raw: str | None) -> list:
    if not raw:
        return []
    try:
        data = json.loads(raw)
        return data if isinstance(data, list) else []
    except (ValueError, TypeError):
        return []
