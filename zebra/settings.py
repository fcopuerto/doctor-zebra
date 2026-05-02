"""Application settings backed by config.cfg + secrets.cfg.

* ``config.cfg``  – non-sensitive metadata (printer name, templates dir,
  per-template overrides, data-source connection options).
* ``secrets.cfg`` – sits next to ``config.cfg`` and only stores
  passwords. It is read/written with permissions ``0600`` on POSIX.

The split keeps the main config friendly to copy / share / version while
keeping secrets out of it.
"""

from __future__ import annotations

import configparser
import os
import stat
from pathlib import Path

_CONNECTION_PREFIX = 'connection_'


class Settings:
    def __init__(self, config_path: str | Path):
        self.config_path = Path(config_path)
        self._cfg = configparser.ConfigParser()
        self._secrets = configparser.ConfigParser()
        self.reload()

    # ---- I/O ---------------------------------------------------------

    @property
    def secrets_path(self) -> Path:
        return self.config_path.with_name('secrets.cfg')

    def reload(self) -> None:
        self._cfg = configparser.ConfigParser()
        self._cfg.read(self.config_path)
        if not self._cfg.has_section('settings'):
            self._cfg.add_section('settings')

        self._secrets = configparser.ConfigParser()
        if self.secrets_path.is_file():
            self._secrets.read(self.secrets_path)

    def _save(self) -> None:
        with self.config_path.open('w') as f:
            self._cfg.write(f)

    def _save_secrets(self) -> None:
        path = self.secrets_path
        with path.open('w') as f:
            self._secrets.write(f)
        # Tighten permissions on POSIX so other users can't read passwords.
        if os.name == 'posix':
            try:
                os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
            except OSError:
                pass

    # ---- Existing settings ------------------------------------------

    @property
    def base_dir(self) -> Path:
        """Directory containing config.cfg — used to resolve relative paths."""
        return self.config_path.parent

    @property
    def templates_dir(self) -> Path:
        raw = self._cfg['settings'].get('templates_dir', 'templates_zpl')
        p = Path(raw)
        if p.is_absolute():
            return p
        return self.base_dir / p

    @property
    def default_printer(self) -> str:
        return self._cfg['settings'].get('printer_name', '')

    @property
    def active_template(self) -> str:
        return self._cfg['settings'].get('zpl_template_path', '')

    def printer_for_template(self, template_file: str) -> str:
        section = f'label_{template_file}'
        if self._cfg.has_section(section):
            return self._cfg[section].get('printer_name', self.default_printer)
        return self.default_printer

    def label_sections(self) -> list[tuple[str, dict]]:
        return [
            (s, dict(self._cfg.items(s)))
            for s in self._cfg.sections()
            if s.startswith('label_')
        ]

    def update_label(self, template_file: str, printer_name: str) -> None:
        section = f'label_{template_file}'
        if not self._cfg.has_section(section):
            self._cfg.add_section(section)
        self._cfg.set(section, 'zpl_template_path', template_file)
        self._cfg.set(section, 'printer_name', printer_name)
        self._cfg['settings']['zpl_template_path'] = template_file
        self._cfg['settings']['printer_name'] = printer_name
        self._save()

    def remove_label(self, template_file: str) -> bool:
        section = f'label_{template_file}'
        if self._cfg.has_section(section):
            self._cfg.remove_section(section)
            self._save()
            return True
        return False

    def set_default_printer(self, printer_name: str) -> None:
        self._cfg['settings']['printer_name'] = printer_name
        self._save()

    def set_templates_dir(self, templates_dir: str) -> None:
        self._cfg['settings']['templates_dir'] = templates_dir
        self._save()

    # ---- Data-source connections -------------------------------------

    def list_connections(self) -> list[tuple[str, str, dict]]:
        out: list[tuple[str, str, dict]] = []
        for section in self._cfg.sections():
            if not section.startswith(_CONNECTION_PREFIX):
                continue
            name = section[len(_CONNECTION_PREFIX):]
            options = {k: v for k, v in self._cfg.items(section) if k != 'type'}
            type_ = self._cfg[section].get('type', 'mssql')
            out.append((name, type_, options))
        return sorted(out, key=lambda t: t[0])

    def get_connection(self, name: str) -> tuple[str, dict] | None:
        section = _CONNECTION_PREFIX + name
        if not self._cfg.has_section(section):
            return None
        options = {k: v for k, v in self._cfg.items(section) if k != 'type'}
        type_ = self._cfg[section].get('type', 'mssql')
        return (type_, options)

    def upsert_connection(self, name: str, type_: str, options: dict) -> None:
        section = _CONNECTION_PREFIX + name
        if not self._cfg.has_section(section):
            self._cfg.add_section(section)
        # Wipe stale keys so removed options actually disappear.
        for key in list(self._cfg[section].keys()):
            self._cfg.remove_option(section, key)
        self._cfg.set(section, 'type', type_)
        for k, v in (options or {}).items():
            if v is None:
                continue
            self._cfg.set(section, k, str(v))
        self._save()

    def remove_connection(self, name: str) -> bool:
        section = _CONNECTION_PREFIX + name
        if self._cfg.has_section(section):
            self._cfg.remove_section(section)
            self._save()
            return True
        return False

    # ---- Connection passwords (secrets.cfg) --------------------------

    def get_connection_password(self, name: str) -> str:
        if self._secrets.has_section(name):
            return self._secrets[name].get('password', '')
        return ''

    def set_connection_password(self, name: str, password: str) -> None:
        if not self._secrets.has_section(name):
            self._secrets.add_section(name)
        self._secrets.set(name, 'password', password or '')
        self._save_secrets()

    def remove_connection_password(self, name: str) -> bool:
        if self._secrets.has_section(name):
            self._secrets.remove_section(name)
            self._save_secrets()
            return True
        return False
