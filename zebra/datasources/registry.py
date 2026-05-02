"""Registry: map ``type`` strings to concrete DataSource classes + helpers
to build a live instance from the saved settings.
"""

from __future__ import annotations

from typing import Type

from zebra.datasources.base import ConnectionConfig, DataSource, DataSourceError
from zebra.datasources.mssql import MSSQLDataSource

_REGISTRY: dict[str, Type[DataSource]] = {
    'mssql': MSSQLDataSource,
}


def available_types() -> list[str]:
    return sorted(_REGISTRY.keys())


def register(type_name: str, cls: Type[DataSource]) -> None:
    """Lets tests inject a stub backend."""
    _REGISTRY[type_name] = cls


def build_datasource(cfg: ConnectionConfig, password: str = '') -> DataSource:
    cls = _REGISTRY.get(cfg.type)
    if cls is None:
        raise DataSourceError(f'Unknown data source type: {cfg.type!r}')
    return cls(cfg, password=password)


# ---------------------------------------------------------------------------
# Settings-backed helpers
# ---------------------------------------------------------------------------

def list_connections(settings) -> list[ConnectionConfig]:
    return [
        ConnectionConfig(name=name, type=type_, options=opts)
        for (name, type_, opts) in settings.list_connections()
    ]


def get_connection(settings, name: str) -> ConnectionConfig | None:
    raw = settings.get_connection(name)
    if not raw:
        return None
    type_, opts = raw
    return ConnectionConfig(name=name, type=type_, options=opts)


def upsert_connection(settings, cfg: ConnectionConfig, password: str | None) -> None:
    settings.upsert_connection(cfg.name, cfg.type, cfg.options)
    if password is not None:
        settings.set_connection_password(cfg.name, password)


def remove_connection(settings, name: str) -> bool:
    settings.remove_connection_password(name)
    return settings.remove_connection(name)
