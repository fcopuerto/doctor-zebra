"""
Offline lookup cache backed by SQLite.

A *lookup* is a named JSON array of objects (e.g. a product catalogue) that
is fetched from an external HTTP source and stored locally so the app works
without network connectivity.

Table schema::

    lookups(name TEXT PK, data TEXT, source_url TEXT, updated_at REAL)
"""
import json
import sqlite3
import time
from contextlib import contextmanager
from typing import Any

import requests

from config import CACHE_DB


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


@contextmanager
def _connection():
    conn = sqlite3.connect(CACHE_DB)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS lookups (
                name       TEXT PRIMARY KEY,
                data       TEXT    NOT NULL,
                source_url TEXT,
                updated_at REAL    NOT NULL
            )
            """
        )
        conn.commit()
        yield conn
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def list_lookups() -> list:
    """Return metadata for all cached lookups (without the full data payload).

    Each item is a dict with keys: ``name``, ``source_url``, ``updated_at``,
    ``count`` (number of records).
    """
    with _connection() as conn:
        rows = conn.execute(
            "SELECT name, source_url, updated_at, data FROM lookups ORDER BY name"
        ).fetchall()
    result = []
    for row in rows:
        data = json.loads(row["data"])
        result.append(
            {
                "name": row["name"],
                "source_url": row["source_url"],
                "updated_at": row["updated_at"],
                "count": len(data) if isinstance(data, list) else 1,
            }
        )
    return result


def get_lookup(name: str) -> Any | None:
    """Return the cached data for *name*, or *None* if not present."""
    with _connection() as conn:
        row = conn.execute(
            "SELECT data FROM lookups WHERE name = ?", (name,)
        ).fetchone()
    if row is None:
        return None
    return json.loads(row["data"])


def set_lookup(name: str, data: Any, source_url: str | None = None) -> None:
    """Insert or replace the lookup named *name* with *data*."""
    with _connection() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO lookups (name, data, source_url, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (name, json.dumps(data, ensure_ascii=False), source_url, time.time()),
        )
        conn.commit()


def delete_lookup(name: str) -> bool:
    """Delete the lookup *name*.  Returns *True* if it existed."""
    with _connection() as conn:
        cursor = conn.execute("DELETE FROM lookups WHERE name = ?", (name,))
        conn.commit()
        return cursor.rowcount > 0


def refresh_lookup(name: str, url: str, timeout: float = 15.0) -> list:
    """Fetch JSON data from *url*, store it in cache and return it.

    Raises:
        requests.HTTPError: if the remote returns a non-2xx status.
        requests.RequestException: on network / timeout errors.
        ValueError: if the response body is not valid JSON.
    """
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    set_lookup(name, data, source_url=url)
    return data


def search_lookup(name: str, query: str, fields: list | None = None) -> list:
    """Case-insensitive substring search inside a cached lookup array.

    *fields* restricts which keys are searched; if *None* all string values
    are searched.  Returns at most 50 matching records.
    """
    data = get_lookup(name)
    if not isinstance(data, list):
        return []
    query_lower = query.lower()
    results = []
    for item in data:
        if not isinstance(item, dict):
            continue
        search_in = (
            [str(item.get(f, "")) for f in fields]
            if fields
            else [str(v) for v in item.values()]
        )
        if any(query_lower in text.lower() for text in search_in):
            results.append(item)
            if len(results) >= 50:
                break
    return results
