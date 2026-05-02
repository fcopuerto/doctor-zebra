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

# Columns added after the original schema. init_db() adds any that are
# missing via ALTER TABLE so existing installations gain them transparently
# without losing data.
_ADDITIVE_COLUMNS: tuple[tuple[str, str], ...] = (
    ('copies',          'INTEGER NOT NULL DEFAULT 1'),
    ('printer_name',    'TEXT'),
    ('status',          "TEXT NOT NULL DEFAULT 'ok'"),
    ('error_message',   'TEXT'),
    ('label_width_mm',  'REAL'),
    ('label_height_mm', 'REAL'),
    ('lookup_key',      'TEXT'),
    ('profile_name',    'TEXT'),
)


def _existing_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f'PRAGMA table_info({table})')}


def _migrate_label_prints(conn: sqlite3.Connection) -> None:
    have = _existing_columns(conn, 'label_prints')
    for name, ddl in _ADDITIVE_COLUMNS:
        if name not in have:
            conn.execute(f'ALTER TABLE label_prints ADD COLUMN {name} {ddl}')

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
        _migrate_label_prints(conn)
        # Helpful index for stats queries that scan by date.
        conn.execute(
            'CREATE INDEX IF NOT EXISTS idx_label_prints_printed_at '
            'ON label_prints(printed_at)'
        )


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------

def insert(
    db_path: str | Path,
    template_file: str,
    fields: dict,
    *,
    copies: int = 1,
    printer_name: str | None = None,
    status: str = 'ok',
    error_message: str | None = None,
    label_width_mm: float | None = None,
    label_height_mm: float | None = None,
    lookup_key: str | None = None,
    profile_name: str | None = None,
) -> int:
    """Insert a print record. ``fields`` is serialised to JSON.

    All metadata beyond ``template_file`` and ``fields`` is optional so
    callers can adopt the richer signature gradually.
    """
    payload = json.dumps(fields or {}, ensure_ascii=False)
    with connect(db_path) as conn:
        cur = conn.execute(
            '''
            INSERT INTO label_prints (
                template_file, fields_json, copies, printer_name,
                status, error_message,
                label_width_mm, label_height_mm,
                lookup_key, profile_name
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                template_file, payload, max(1, int(copies or 1)), printer_name,
                status, error_message,
                label_width_mm, label_height_mm,
                lookup_key, profile_name,
            ),
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


# ---------------------------------------------------------------------------
# Stats (Dashboard)
# ---------------------------------------------------------------------------
#
# All counts use SUM(copies) — what users care about is "labels printed",
# not "jobs sent". Failed jobs are excluded by default since the user thinks
# of those as "labels NOT printed"; pass include_errors=True to count them
# (e.g. for the recent-errors panel which needs the raw rows anyway).

def _kpi_sum(conn: sqlite3.Connection, since_iso: str | None) -> int:
    where = "WHERE status = 'ok'"
    args: tuple = ()
    if since_iso:
        where += ' AND printed_at >= ?'
        args = (since_iso,)
    row = conn.execute(
        f'SELECT COALESCE(SUM(copies), 0) FROM label_prints {where}',
        args,
    ).fetchone()
    return int(row[0] or 0)


def kpi_counts(db_path: str | Path) -> dict:
    """Return ``{today, week, month, total}`` — labels printed (sum of copies).

    ``week``/``month`` are *rolling* windows (last 7 / 30 days), which is more
    useful than calendar week/month for an operational dashboard.
    """
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = now - timedelta(days=7)
    month_start = now - timedelta(days=30)

    fmt = '%Y-%m-%d %H:%M:%S'
    with connect(db_path) as conn:
        return {
            'today': _kpi_sum(conn, today_start.strftime(fmt)),
            'week':  _kpi_sum(conn, week_start.strftime(fmt)),
            'month': _kpi_sum(conn, month_start.strftime(fmt)),
            'total': _kpi_sum(conn, None),
        }


def daily_activity(db_path: str | Path, days: int = 30) -> list[dict]:
    """Return one entry per day for the last ``days`` days, oldest first.

    Each entry is ``{date: 'YYYY-MM-DD', count: int}``. Days with zero prints
    are included (so the chart has a continuous x-axis).
    """
    from datetime import date, timedelta
    days = max(1, int(days))
    today = date.today()
    start = today - timedelta(days=days - 1)

    with connect(db_path) as conn:
        rows = conn.execute(
            '''
            SELECT date(printed_at) AS d, COALESCE(SUM(copies), 0) AS n
            FROM label_prints
            WHERE status = 'ok' AND date(printed_at) >= ?
            GROUP BY d
            ''',
            (start.isoformat(),),
        ).fetchall()
    by_day = {r[0]: int(r[1]) for r in rows}

    out: list[dict] = []
    for i in range(days):
        d = (start + timedelta(days=i)).isoformat()
        out.append({'date': d, 'count': by_day.get(d, 0)})
    return out


def top_templates(db_path: str | Path, limit: int = 5) -> list[dict]:
    with connect(db_path) as conn:
        rows = conn.execute(
            '''
            SELECT template_file, SUM(copies) AS n
            FROM label_prints
            WHERE status = 'ok'
            GROUP BY template_file
            ORDER BY n DESC
            LIMIT ?
            ''',
            (limit,),
        ).fetchall()
    return [{'template_file': r[0], 'count': int(r[1])} for r in rows]


def top_sizes(db_path: str | Path, limit: int = 5) -> list[dict]:
    """Top label sizes. Rows with no dimensions are bucketed as ``unknown``."""
    with connect(db_path) as conn:
        rows = conn.execute(
            '''
            SELECT label_width_mm, label_height_mm, SUM(copies) AS n
            FROM label_prints
            WHERE status = 'ok'
            GROUP BY label_width_mm, label_height_mm
            ORDER BY n DESC
            LIMIT ?
            ''',
            (limit,),
        ).fetchall()
    out: list[dict] = []
    for w, h, n in rows:
        if w is None and h is None:
            label = 'unknown'
        elif w is not None and h is not None:
            label = f'{w:g} × {h:g} mm'
        else:
            label = f'{(w or h):g} mm'
        out.append({'label': label, 'count': int(n)})
    return out


def top_printers(db_path: str | Path, limit: int = 5) -> list[dict]:
    with connect(db_path) as conn:
        rows = conn.execute(
            '''
            SELECT COALESCE(NULLIF(printer_name, ''), '(unset)') AS p,
                   SUM(copies) AS n
            FROM label_prints
            WHERE status = 'ok'
            GROUP BY p
            ORDER BY n DESC
            LIMIT ?
            ''',
            (limit,),
        ).fetchall()
    return [{'printer_name': r[0], 'count': int(r[1])} for r in rows]


def recent_errors(db_path: str | Path, limit: int = 10) -> list[dict]:
    with connect(db_path) as conn:
        rows = conn.execute(
            '''
            SELECT printed_at, template_file, printer_name, error_message, copies
            FROM label_prints
            WHERE status = 'error'
            ORDER BY printed_at DESC
            LIMIT ?
            ''',
            (limit,),
        ).fetchall()
    return [
        {
            'printed_at': r[0],
            'template_file': r[1],
            'printer_name': r[2] or '(unset)',
            'error_message': r[3] or '',
            'copies': int(r[4] or 1),
        }
        for r in rows
    ]
