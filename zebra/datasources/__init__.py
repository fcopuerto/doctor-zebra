"""Pluggable data sources for lookup fields.

A DataSource hides "where do my products live" behind a small interface so
the rest of the app can work with CSV files, SQL Server tables or anything
else through the same calls.
"""

from zebra.datasources.base import DataSource, DataSourceError, ConnectionConfig
from zebra.datasources.mssql import MSSQLDataSource
from zebra.datasources.registry import (
    available_types, build_datasource, list_connections, get_connection,
    upsert_connection, remove_connection,
)

__all__ = [
    'DataSource',
    'DataSourceError',
    'ConnectionConfig',
    'MSSQLDataSource',
    'available_types',
    'build_datasource',
    'list_connections',
    'get_connection',
    'upsert_connection',
    'remove_connection',
]
