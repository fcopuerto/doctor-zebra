"""Abstract data source contract.

Any concrete data source (SQL Server, MySQL, CSV, ...) implements this so
lookup fields and the connection UI can stay backend-agnostic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class DataSourceError(Exception):
    """Raised by data source implementations on connection / query failure."""


@dataclass
class ConnectionConfig:
    """Plain-data description of a saved connection.

    Sensitive bits (password) are passed in via the ``password`` argument
    when building a live :class:`DataSource`; they are not part of this
    object so it can be serialised to ``config.cfg`` safely.
    """
    name: str
    type: str
    options: dict[str, str] = field(default_factory=dict)

    def get(self, key: str, default: str = '') -> str:
        return str(self.options.get(key, default) or '')

    def to_dict(self) -> dict:
        return {'name': self.name, 'type': self.type, 'options': dict(self.options)}


class DataSource:
    """Common interface every backend implements."""

    def __init__(self, cfg: ConnectionConfig, password: str = ''):
        self.cfg = cfg
        self.password = password

    @property
    def name(self) -> str:
        return self.cfg.name

    # --- to be implemented by concrete classes ----------------------------

    def test(self) -> tuple[bool, str]:
        """Quick reachability check. Returns (ok, message)."""
        raise NotImplementedError

    def list_tables(self) -> list[dict]:
        """Return ``[{'name': 'schema.object', 'kind': 'table'|'view'}, ...]``.

        Both tables and views are reported so lookup fields can be bound to
        either. Concrete backends should sort the result and use the
        qualified ``schema.object`` form.
        """
        raise NotImplementedError

    def list_columns(self, table: str) -> list[str]:
        raise NotImplementedError

    def search(
        self,
        table: str,
        search_columns: list[str],
        query: str,
        return_columns: list[str] | None = None,
        limit: int = 25,
    ) -> list[dict[str, Any]]:
        """Free-text search across ``search_columns`` returning matching rows."""
        raise NotImplementedError

    def lookup_row(
        self,
        table: str,
        key_column: str,
        key_value: str,
        return_columns: list[str] | None = None,
    ) -> dict[str, Any] | None:
        """Fetch a single row by exact key. Returns ``None`` when not found."""
        raise NotImplementedError

    def fetch_all(
        self,
        table: str,
        return_columns: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Return every row of ``table`` (used to populate the offline cache).

        Backends may stream internally but must materialise the result as a
        list[dict] so the cache layer can persist it.
        """
        raise NotImplementedError
