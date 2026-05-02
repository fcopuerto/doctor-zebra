"""SQL Server data source.

Two interchangeable drivers are supported and auto-selected from the
saved options or the environment:

* ``pyodbc`` — recommended on Windows. Uses the Microsoft ODBC Driver 18
  which ships with Windows Update. Supports Windows / AD authentication.
* ``pymssql`` — pure-Python (uses FreeTDS internally). Works on
  macOS / Linux / Windows with a single ``pip install`` and no Microsoft
  component required. Doesn't support Windows authentication.

The user picks one in the connection form (``driver_lib`` field) or the
backend falls back to whichever is importable.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

from zebra.datasources.base import ConnectionConfig, DataSource, DataSourceError


# ---------------------------------------------------------------------------
# Driver discovery
# ---------------------------------------------------------------------------

def _has_pyodbc() -> bool:
    try:
        import pyodbc  # noqa: F401
        return True
    except ImportError:
        return False


def _has_pymssql() -> bool:
    try:
        import pymssql  # noqa: F401
        return True
    except ImportError:
        return False


def _pick_driver(preferred: str = '') -> str:
    """Return the driver actually available, honouring user preference."""
    pref = (preferred or '').lower().strip()
    if pref == 'pyodbc' and _has_pyodbc():
        return 'pyodbc'
    if pref == 'pymssql' and _has_pymssql():
        return 'pymssql'
    if _has_pyodbc():
        return 'pyodbc'
    if _has_pymssql():
        return 'pymssql'
    return ''


def _int(raw, default: int) -> int:
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


_INSTALL_HELP_SOURCE = (
    'No SQL Server driver is available. Pick whichever fits your machine:\n'
    '  • pymssql (pure-Python, works on Mac/Linux/Windows, no Microsoft '
    'components):  pip install -r requirements-mssql-pure.txt\n'
    '  • pyodbc + Microsoft ODBC Driver 18 (recommended on Windows; '
    'supports Windows authentication):  pip install -r '
    'requirements-mssql-odbc.txt'
)

_INSTALL_HELP_FROZEN = (
    'No SQL Server driver is bundled with this build. Use a release that '
    'includes pymssql, or for Windows Authentication install the Microsoft '
    'ODBC Driver 18 system-wide and use a build that includes pyodbc.'
)


def is_frozen() -> bool:
    """True when running inside a PyInstaller bundle (.exe / .app)."""
    return bool(getattr(sys, 'frozen', False))


def driver_status() -> dict:
    """Quick snapshot used by the UI to show what's installed."""
    frozen = is_frozen()
    return {
        'pyodbc': _has_pyodbc(),
        'pymssql': _has_pymssql(),
        'frozen': frozen,
        'help': _INSTALL_HELP_FROZEN if frozen else _INSTALL_HELP_SOURCE,
    }


# ---------------------------------------------------------------------------
# Connection-string builders
# ---------------------------------------------------------------------------

def build_connection_string(cfg: ConnectionConfig, password: str = '') -> str:
    """ODBC connection string for pyodbc."""
    driver = cfg.get('driver') or 'ODBC Driver 18 for SQL Server'
    server = cfg.get('server')
    port = cfg.get('port', '1433')
    database = cfg.get('database')

    if not server:
        raise DataSourceError('Server is required.')
    if not database:
        raise DataSourceError('Database is required.')

    server_part = server if ('\\' in server or ',' in server) else f'{server},{port}'

    parts = [
        f'DRIVER={{{driver}}}',
        f'SERVER={server_part}',
        f'DATABASE={database}',
    ]
    if cfg.get('encrypt', 'yes').lower() in ('yes', 'true', '1'):
        parts.append('Encrypt=yes')
    else:
        parts.append('Encrypt=no')
    if cfg.get('trust_server_certificate', 'yes').lower() in ('yes', 'true', '1'):
        parts.append('TrustServerCertificate=yes')

    auth = (cfg.get('auth') or 'sql').lower()
    if auth == 'windows':
        parts.append('Trusted_Connection=yes')
    else:
        username = cfg.get('username')
        if not username:
            raise DataSourceError('Username is required for SQL authentication.')
        parts.append(f'UID={username}')
        parts.append(f'PWD={password}')

    timeout = cfg.get('timeout', '5')
    parts.append(f'Connection Timeout={timeout}')

    return ';'.join(parts) + ';'


# ---------------------------------------------------------------------------
# Backend
# ---------------------------------------------------------------------------

class MSSQLDataSource(DataSource):
    type = 'mssql'

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def _driver(self) -> str:
        return _pick_driver(self.cfg.get('driver_lib'))

    def _connect(self):
        driver = self._driver()
        if not driver:
            raise DataSourceError(_INSTALL_HELP)
        if driver == 'pyodbc':
            return self._connect_pyodbc()
        return self._connect_pymssql()

    def _connect_pyodbc(self):
        import pyodbc  # type: ignore
        conn_str = build_connection_string(self.cfg, self.password)
        try:
            return pyodbc.connect(conn_str, timeout=_int(self.cfg.get('timeout'), 5))
        except pyodbc.Error as e:
            raise DataSourceError(self._friendly_pyodbc(e)) from e

    def _connect_pymssql(self):
        import pymssql  # type: ignore
        if (self.cfg.get('auth') or 'sql').lower() == 'windows':
            raise DataSourceError(
                'Windows authentication requires the pyodbc driver. '
                'Either switch to SQL authentication or install pyodbc + '
                'Microsoft ODBC Driver 18.'
            )
        try:
            return pymssql.connect(
                server=self.cfg.get('server'),
                port=_int(self.cfg.get('port'), 1433),
                database=self.cfg.get('database'),
                user=self.cfg.get('username'),
                password=self.password or '',
                login_timeout=_int(self.cfg.get('timeout'), 5),
                charset='UTF-8',
            )
        except Exception as e:  # pymssql.OperationalError, etc.
            raise DataSourceError(self._friendly_pymssql(e)) from e

    @staticmethod
    def _friendly_pyodbc(err: Exception) -> str:
        msg = str(err)
        if 'IM002' in msg:
            return ('Microsoft ODBC Driver 18 is not installed.\n'
                    'On Windows it usually comes with Windows Update; if it '
                    'doesn\'t, download it from '
                    'https://learn.microsoft.com/sql/connect/odbc/.\n'
                    'On macOS:  brew tap microsoft/mssql-release && '
                    'brew install msodbcsql18.\n'
                    'Or switch the connection driver to "pymssql" '
                    '(no Microsoft components needed).')
        if '08001' in msg or '08S01' in msg:
            return ('Cannot reach the SQL Server. Check that the host is '
                    'correct, the port is open and any firewall allows it.')
        if '28000' in msg:
            return 'Login failed. Check user, password and authentication mode.'
        return msg

    @staticmethod
    def _friendly_pymssql(err: Exception) -> str:
        msg = str(err)
        if 'Adaptive Server' in msg or '20009' in msg or 'connect' in msg.lower():
            return ('Cannot reach the SQL Server through pymssql. '
                    'Check host, port and credentials, and that the server '
                    'allows TCP connections.')
        return msg

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def test(self) -> tuple[bool, str]:
        try:
            with self._connect() as conn:
                cur = conn.cursor()
                cur.execute('SELECT 1')
                cur.fetchone()
            return (
                True,
                f'Connected via {self._driver()} to '
                f'{self.cfg.get("server")}/{self.cfg.get("database")}',
            )
        except DataSourceError as e:
            return (False, str(e))
        except Exception as e:  # defensive
            logging.exception('Unexpected MSSQL test failure')
            return (False, f'Unexpected error: {e}')

    def list_tables(self) -> list[dict]:
        sql = (
            "SELECT TABLE_SCHEMA + '.' + TABLE_NAME, TABLE_TYPE "
            "FROM INFORMATION_SCHEMA.TABLES "
            "WHERE TABLE_TYPE IN ('BASE TABLE', 'VIEW') "
            "ORDER BY TABLE_TYPE DESC, TABLE_SCHEMA, TABLE_NAME"
        )
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(sql)
            return [
                {'name': row[0], 'kind': 'view' if row[1] == 'VIEW' else 'table'}
                for row in cur.fetchall()
            ]

    def list_columns(self, table: str) -> list[str]:
        schema, _, name = table.partition('.')
        if not name:
            schema, name = 'dbo', table
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                "WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s "
                "ORDER BY ORDINAL_POSITION"
                if self._driver() == 'pymssql'
                else "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                     "WHERE TABLE_SCHEMA=? AND TABLE_NAME=? "
                     "ORDER BY ORDINAL_POSITION",
                (schema, name),
            )
            return [row[0] for row in cur.fetchall()]

    # ---- queries -----------------------------------------------------

    def search(
        self,
        table: str,
        search_columns: list[str],
        query: str,
        return_columns: list[str] | None = None,
        limit: int = 25,
    ) -> list[dict[str, Any]]:
        if not search_columns:
            return []
        cols = return_columns or search_columns
        select = ', '.join(self._quote(c) for c in cols)
        ph = self._param_placeholder()
        where = ' OR '.join(f'{self._quote(c)} LIKE {ph}' for c in search_columns)
        sql = (
            f'SELECT TOP ({int(limit)}) {select} FROM {self._quote_table(table)} '
            f'WHERE {where}'
        )
        like = f'%{query}%'
        params = tuple([like] * len(search_columns))
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(sql, params)
            return [dict(zip(cols, row)) for row in cur.fetchall()]

    def lookup_row(
        self,
        table: str,
        key_column: str,
        key_value: str,
        return_columns: list[str] | None = None,
    ) -> dict[str, Any] | None:
        cols = return_columns or [key_column]
        select = ', '.join(self._quote(c) for c in cols)
        ph = self._param_placeholder()
        sql = (
            f'SELECT TOP 1 {select} FROM {self._quote_table(table)} '
            f'WHERE {self._quote(key_column)} = {ph}'
        )
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(sql, (key_value,))
            row = cur.fetchone()
        return dict(zip(cols, row)) if row else None

    def fetch_all(
        self,
        table: str,
        return_columns: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        cols = return_columns or self.list_columns(table)
        if not cols:
            return []
        select = ', '.join(self._quote(c) for c in cols)
        sql = f'SELECT {select} FROM {self._quote_table(table)}'
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(sql)
            return [dict(zip(cols, row)) for row in cur.fetchall()]

    # ------------------------------------------------------------------
    # Quoting / placeholders
    # ------------------------------------------------------------------

    def _param_placeholder(self) -> str:
        return '%s' if self._driver() == 'pymssql' else '?'

    @staticmethod
    def _quote(ident: str) -> str:
        return '[' + ident.replace(']', ']]') + ']'

    @classmethod
    def _quote_table(cls, table: str) -> str:
        if '.' in table:
            schema, name = table.split('.', 1)
            return f'{cls._quote(schema)}.{cls._quote(name)}'
        return cls._quote(table)
