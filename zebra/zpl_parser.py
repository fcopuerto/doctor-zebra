"""Parse ZPL produced by ZebraDesigner (or any tool) into a structured list.

The goal is to let the user import a finished, well-formed ZPL label and
identify every static string that could become a variable at print time.

Only ``^FD...^FS`` blocks carry the human-authored content; we scan
backwards from each one to pick up the most relevant preceding command
(`^B*` barcode definitions, `^GB` graphic box, `^FO` position) so the
import UI can tag each literal with its type.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from typing import Iterable

# ^FD (field data) begins, followed by any chars, until ^FS (field separator).
# Non-greedy, DOTALL so newlines inside data are kept.
_FD_RE = re.compile(r'\^FD(.*?)\^FS', re.DOTALL)

# Position command: ^FOx,y or ^FTx,y or ^FOx,y,z
_POS_RE = re.compile(r'\^(?:FO|FT)(\d+),(\d+)')

# Barcode command precedes the ^FD and lives on the same "field".
# Map the first letter after ^B to a human label.
_BARCODE_TYPES = {
    'C': 'code128',
    'E': 'ean13',
    '8': 'ean8',
    '3': 'code39',
    'Q': 'qr',
    'X': 'datamatrix',
    'K': 'codabar',
    '7': 'pdf417',
    'Z': 'pdf417',
    'U': 'upc_a',
    '9': 'upc_e',
    'A': 'code93',
    'I': 'interleaved25',
}

# Barcode detector: ^B<letter>[...]. We scan backwards from each ^FD to find
# the nearest one within ~200 chars (a single ZPL "field" is much shorter).
_BARCODE_RE = re.compile(r'\^B([A-Z0-9])[A-Z0-9,.\-]*')


@dataclass
class FDBlock:
    index: int              # 0-based order within the file
    start: int              # offset of the "^FD" itself
    end: int                # offset just past the "^FS"
    data: str               # the literal between ^FD and ^FS
    barcode: str | None     # "code128" / "qr" / ... or None for plain text
    position: tuple[int, int] | None  # (x, y) from the nearest ^FO/^FT
    suggested_key: str      # sanitised slug derived from the data

    def to_dict(self) -> dict:
        d = asdict(self)
        d['position'] = list(self.position) if self.position else None
        return d


def parse_fd_blocks(zpl: str) -> list[FDBlock]:
    """Return every ``^FD...^FS`` literal together with its context."""
    blocks: list[FDBlock] = []
    for idx, match in enumerate(_FD_RE.finditer(zpl)):
        data = match.group(1)
        start, end = match.start(), match.end()
        barcode = _barcode_before(zpl, start)
        position = _position_before(zpl, start)
        blocks.append(FDBlock(
            index=idx,
            start=start,
            end=end,
            data=data,
            barcode=barcode,
            position=position,
            suggested_key=_slugify(data) or f'field_{idx + 1}',
        ))
    return blocks


def already_parameterised(block: FDBlock) -> bool:
    """True when the block's data already contains a ``{placeholder}``."""
    return bool(re.search(r'\{[a-zA-Z_][a-zA-Z0-9_]*\}', block.data))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _barcode_before(zpl: str, fd_pos: int, window: int = 220) -> str | None:
    """Look back ``window`` chars for the closest ``^B<letter>`` command."""
    start = max(0, fd_pos - window)
    chunk = zpl[start:fd_pos]
    last: re.Match | None = None
    for m in _BARCODE_RE.finditer(chunk):
        last = m
    if not last:
        return None
    letter = last.group(1)
    return _BARCODE_TYPES.get(letter, f'b{letter.lower()}')


def _position_before(zpl: str, fd_pos: int, window: int = 220) -> tuple[int, int] | None:
    """Nearest ``^FO``/``^FT`` before the ^FD; used for display sorting."""
    start = max(0, fd_pos - window)
    chunk = zpl[start:fd_pos]
    last: re.Match | None = None
    for m in _POS_RE.finditer(chunk):
        last = m
    if not last:
        return None
    return (int(last.group(1)), int(last.group(2)))


def _slugify(text: str) -> str:
    """Suggest a plausible field key from a literal value."""
    # Strip things that aren't letters/digits/underscores
    s = re.sub(r'[^a-zA-Z0-9_]+', '_', text.strip())
    s = re.sub(r'_+', '_', s).strip('_').lower()
    # Keys must start with a letter
    if s and s[0].isdigit():
        s = 'f_' + s
    return s[:40]


def rewrite_with_placeholders(zpl: str, mapping: dict[int, str]) -> str:
    """Return ``zpl`` with selected ^FD blocks replaced by ``{key}`` placeholders.

    Parameters
    ----------
    zpl
        Original ZPL text.
    mapping
        ``{block_index: field_key}``. Blocks not present in the mapping are
        kept verbatim.
    """
    if not mapping:
        return zpl
    blocks = parse_fd_blocks(zpl)
    # Walk right-to-left so offsets stay valid as we splice.
    out = zpl
    for block in sorted(blocks, key=lambda b: b.start, reverse=True):
        key = mapping.get(block.index)
        if not key:
            continue
        replacement = f'^FD{{{key}}}^FS'
        out = out[:block.start] + replacement + out[block.end:]
    return out


def blocks_to_sidecar_fields(
    blocks: Iterable[FDBlock],
    selected: dict[int, str],
) -> list[dict]:
    """Build a sidecar ``fields`` list from the user's selection.

    The original literal becomes the placeholder so the form has a hint
    of what should go there. ``default`` stays empty so the field is
    blank on first render and the user has to type/pick a value — except
    when the source ZPL already had a ``{placeholder}`` token, which is
    not a sensible default to show in the form.
    """
    out: list[dict] = []
    seen: set[str] = set()
    for block in blocks:
        key = selected.get(block.index)
        if not key or key in seen:
            continue
        seen.add(key)
        placeholder = '' if already_parameterised(block) else block.data
        field = {
            'key': key,
            'label': _humanise(key),
            'default': '',
            'placeholder': placeholder,
            'required': False,
            'multiline': '\n' in block.data,
        }
        if block.barcode:
            field['barcode'] = block.barcode
        out.append(field)
    return out


def _humanise(key: str) -> str:
    return key.replace('_', ' ').strip().title()
