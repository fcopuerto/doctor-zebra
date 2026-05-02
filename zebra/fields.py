"""Per-template field definitions.

Each ZPL template exposes a list of :class:`FieldSpec` records that drive
the dynamic form in the UI. Definitions come from two sources:

1. **Sidecar JSON** — ``<template>.json`` next to the ZPL file. When
   present it is authoritative.
2. **Auto-detection** — when no sidecar exists, placeholders in the ZPL
   (e.g. ``{recipient_name}``) are promoted to plain text fields with
   titleised labels.

The sidecar format::

    {
        "fields": [
            {
                "key": "recipient_name",
                "label": "Nombre",
                "default": "",
                "placeholder": "Juan Pérez",
                "required": true,
                "multiline": false
            }
        ]
    }
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field, asdict


def field_factory_list():
    return field(default_factory=list)


def field_factory_dict():
    return field(default_factory=dict)


def _str_list(raw) -> list:
    if not raw:
        return []
    if isinstance(raw, str):
        return [s.strip() for s in raw.split(',') if s.strip()]
    return [str(s).strip() for s in raw if str(s).strip()]


def _str_dict(raw) -> dict:
    if not raw:
        return {}
    if isinstance(raw, dict):
        return {str(k): str(v) for k, v in raw.items() if k and v}
    return {}
from pathlib import Path

_PLACEHOLDER_RE = re.compile(r'\{([a-zA-Z_][a-zA-Z0-9_]*)\}')
_KEY_RE = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')


@dataclass
class FieldSpec:
    key: str
    label: str = ''
    default: str = ''
    placeholder: str = ''
    required: bool = False
    multiline: bool = False
    barcode: str = ''  # 'code128' | 'ean13' | 'qr' | 'datamatrix' | 'code39' | '' (none)

    # Field type: 'text' (free input) or 'lookup' (autocomplete against a DB).
    type: str = 'text'

    # ---- Lookup configuration (only used when ``type == 'lookup'``) ------
    source: str = ''                                    # connection name
    table: str = ''                                     # 'schema.table'
    search_columns: list[str] = field_factory_list()    # columns to LIKE %q%
    display_columns: list[str] = field_factory_list()   # columns shown in dropdown
    value_column: str = ''                              # column whose value goes into the input
    autofill: dict[str, str] = field_factory_dict()     # other_field_key -> db_column

    def __post_init__(self):
        if not self.label:
            self.label = _humanise(self.key)
        if self.type not in ('text', 'lookup'):
            self.type = 'text'

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'FieldSpec':
        key = (data.get('key') or '').strip()
        if not _KEY_RE.match(key):
            raise ValueError(f"Invalid field key: {key!r}")
        return cls(
            key=key,
            label=(data.get('label') or '').strip(),
            default=str(data.get('default') or ''),
            placeholder=str(data.get('placeholder') or ''),
            required=bool(data.get('required')),
            multiline=bool(data.get('multiline')),
            barcode=str(data.get('barcode') or ''),
            type=str(data.get('type') or 'text'),
            source=str(data.get('source') or ''),
            table=str(data.get('table') or ''),
            search_columns=_str_list(data.get('search_columns')),
            display_columns=_str_list(data.get('display_columns')),
            value_column=str(data.get('value_column') or ''),
            autofill=_str_dict(data.get('autofill')),
        )


def _humanise(key: str) -> str:
    return key.replace('_', ' ').strip().title()


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def sidecar_path(template_path: Path) -> Path:
    """Return the sidecar JSON path for a given ``.zpl`` file."""
    return template_path.with_suffix(template_path.suffix + '.json')


def autodetect_from_zpl(zpl_text: str) -> list[FieldSpec]:
    """Return a :class:`FieldSpec` list built from ``{placeholder}`` tokens."""
    seen: list[str] = []
    for match in _PLACEHOLDER_RE.finditer(zpl_text):
        key = match.group(1)
        if key not in seen:
            seen.append(key)
    return [FieldSpec(key=k) for k in seen]


def load_sidecar(template_path: Path) -> list[FieldSpec] | None:
    """Return field specs from the sidecar JSON, or ``None`` if absent."""
    p = sidecar_path(template_path)
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text())
        raw = data.get('fields') or []
        return [FieldSpec.from_dict(item) for item in raw]
    except (OSError, ValueError, TypeError) as e:
        logging.warning(f"Ignoring invalid sidecar {p.name}: {e}")
        return None


def save_sidecar(template_path: Path, specs: list[FieldSpec]) -> None:
    """Persist field specs to the sidecar JSON next to the template."""
    payload = {'fields': [s.to_dict() for s in specs]}
    sidecar_path(template_path).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + '\n',
        encoding='utf-8',
    )


def remove_sidecar(template_path: Path) -> bool:
    """Delete the sidecar JSON if it exists."""
    p = sidecar_path(template_path)
    if p.is_file():
        p.unlink()
        return True
    return False


def load_fields(template_path: Path) -> list[FieldSpec]:
    """Resolve the field specs for a template (sidecar first, autodetect fallback)."""
    sidecar = load_sidecar(template_path)
    if sidecar is not None:
        return sidecar
    try:
        zpl_text = template_path.read_text()
    except OSError as e:
        logging.error(f"Cannot read template {template_path}: {e}")
        return []
    return autodetect_from_zpl(zpl_text)


def specs_to_defaults(specs: list[FieldSpec]) -> dict[str, str]:
    """Return ``{key: default}`` for pre-filling a blank form."""
    return {s.key: s.default for s in specs}


def sanitize_values(specs: list[FieldSpec], form: dict) -> dict[str, str]:
    """Pick only known keys from ``form``, falling back to defaults."""
    return {s.key: str(form.get(s.key, s.default) or '') for s in specs}
