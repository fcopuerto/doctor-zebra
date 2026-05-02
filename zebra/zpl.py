"""ZPL template discovery, validation, sanitization, and rendering."""

import logging
import re
from pathlib import Path

# Strip ZPL command chars from user values to prevent command injection.
_ZPL_CONTROL_CHARS = str.maketrans({'^': '', '~': ''})

# Zebra printers default to 203 dpi (8 dots/mm). 300dpi exists but is rare
# in this app's target installs; keeping it as a constant means stats
# stay comparable across runs for the same template.
_DEFAULT_DPI = 203
_MM_PER_INCH = 25.4

_PW_RE = re.compile(r'\^PW(\d+)', re.IGNORECASE)
_LL_RE = re.compile(r'\^LL(\d+)', re.IGNORECASE)


def label_dimensions_mm(
    zpl_text: str, dpi: int = _DEFAULT_DPI
) -> tuple[float | None, float | None]:
    """Return ``(width_mm, height_mm)`` parsed from ``^PW`` / ``^LL`` commands.

    Either component is ``None`` when the command isn't present — common for
    fragments that rely on the printer's persistent settings.
    """
    if not zpl_text:
        return (None, None)
    pw = _PW_RE.search(zpl_text)
    ll = _LL_RE.search(zpl_text)
    width = round(int(pw.group(1)) * _MM_PER_INCH / dpi, 1) if pw else None
    height = round(int(ll.group(1)) * _MM_PER_INCH / dpi, 1) if ll else None
    return (width, height)


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
