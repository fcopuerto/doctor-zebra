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
_PQ_RE = re.compile(r'(\^PQ)(\d+)', re.IGNORECASE)
_XZ_RE = re.compile(r'\^XZ', re.IGNORECASE)


def with_print_quantity(zpl: str, copies: int) -> str:
    """Return ``zpl`` annotated with ``^PQn`` so the printer prints n copies.

    Sending the format string N times forces the printer to re-parse and
    re-render every copy, which is wasteful and noticeably slow on
    USB/network links. ``^PQ`` tells the firmware to keep the buffered
    label and emit ``copies`` of it — one wire payload, one parse, N
    physical labels.

    Behaviour:
      * ``copies <= 1`` → returned unchanged.
      * Existing ``^PQ`` → only the quantity argument is rewritten;
        any pause/replicate/override params (``,p,r,o``) are preserved.
      * No ``^PQ`` → ``^PQ<copies>`` is inserted right before the last
        ``^XZ``. If the input has no ``^XZ`` (malformed), the command
        is appended at the end.
    """
    if copies is None or copies <= 1:
        return zpl
    if _PQ_RE.search(zpl):
        return _PQ_RE.sub(rf'\g<1>{copies}', zpl, count=1)
    matches = list(_XZ_RE.finditer(zpl))
    if matches:
        pos = matches[-1].start()
        return zpl[:pos] + f'^PQ{copies}\n' + zpl[pos:]
    return zpl + f'\n^PQ{copies}'


def inject_print_settings(zpl: str, settings: dict | None) -> str:
    """Prepend/insert printer-control commands into a rendered ZPL block.

    Three knobs are supported, each with an "inherit" sentinel that skips
    the command (so the printer's default or whatever the template already
    has stays in place):

      ``media_type``: ``'thermal'`` → ``^MTD`` (direct thermal),
                      ``'ribbon'``  → ``^MTT`` (thermal transfer),
                      ``''`` → no override.
      ``speed_ips``:  1..14 → ``^PRn`` (ips); 0 → no override.
      ``darkness``:   0..30 → ``~SDnn``; -1 → no override.

    ``~SD`` is a ``~`` system command — has to live before ``^XA``.
    ``^MT`` and ``^PR`` are format commands — go right after ``^XA``.
    """
    if not settings:
        return zpl

    pre_xa: list[str] = []
    post_xa: list[str] = []

    mt = (settings.get('media_type') or '').strip().lower()
    if mt == 'thermal':
        post_xa.append('^MTD')
    elif mt == 'ribbon':
        post_xa.append('^MTT')

    try:
        speed = int(settings.get('speed_ips') or 0)
    except (TypeError, ValueError):
        speed = 0
    if 1 <= speed <= 14:
        post_xa.append(f'^PR{speed}')

    try:
        darkness = int(settings.get('darkness'))
    except (TypeError, ValueError):
        darkness = -1
    if 0 <= darkness <= 30:
        pre_xa.append(f'~SD{darkness:02d}')

    if not pre_xa and not post_xa:
        return zpl

    result = zpl
    if post_xa and '^XA' in result:
        result = result.replace('^XA', '^XA\n' + '\n'.join(post_xa), 1)
    if pre_xa:
        result = '\n'.join(pre_xa) + '\n' + result
    return result


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
    return render_text(template_path.read_text(), fields,
                       label=template_path.name)


def render_text(raw: str, fields: dict, label: str = '<inline>') -> str:
    """Render a ZPL string (already loaded) with the given field map."""
    safe = {k: clean_field(v) for k, v in fields.items()}
    try:
        return raw.format_map(_SafeDict(safe))
    except (IndexError, ValueError) as e:
        logging.error(f"Malformed ZPL template {label}: {e}")
        return raw
