"""ZPL template discovery, validation, sanitization, and rendering."""

import logging
from pathlib import Path

# Strip ZPL command chars from user values to prevent command injection.
_ZPL_CONTROL_CHARS = str.maketrans({'^': '', '~': ''})


def clean_field(value: str) -> str:
    return (value or '').translate(_ZPL_CONTROL_CHARS)


class _SafeDict(dict):
    def __missing__(self, key):
        return ''


def list_templates(templates_dir: Path) -> list[str]:
    if not templates_dir.is_dir():
        logging.warning(f"Templates directory does not exist: {templates_dir}")
        return []
    return sorted(p.name for p in templates_dir.iterdir() if p.suffix == '.zpl')


def resolve_template(templates_dir: Path, template_file: str) -> Path | None:
    """Return the safe path to a template, or None if it isn't whitelisted."""
    if not template_file or template_file not in list_templates(templates_dir):
        return None
    return templates_dir / template_file


def render(template_path: Path, fields: dict) -> str:
    raw = template_path.read_text()
    safe = {k: clean_field(v) for k, v in fields.items()}
    try:
        return raw.format_map(_SafeDict(safe))
    except (IndexError, ValueError) as e:
        logging.error(f"Malformed ZPL template {template_path.name}: {e}")
        return raw
