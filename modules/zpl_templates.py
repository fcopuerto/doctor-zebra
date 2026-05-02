"""
ZPL template management.

Each template is stored as a plain-text ``.zpl`` file inside
``data/zpl_templates/``.  Variable placeholders use ``{variable_name}``
syntax (single curly braces), which are substituted at print time via
:func:`modules.printer.render_template`.
"""
import os
import re

from config import TEMPLATES_DIR
from modules.printer import extract_variables  # noqa: re-export

os.makedirs(TEMPLATES_DIR, exist_ok=True)

_SAFE_NAME = re.compile(r"^[A-Za-z0-9_\-]+$")


def _safe(name: str) -> str:
    if not _SAFE_NAME.match(name):
        raise ValueError(f"Invalid template name: {name!r}")
    return name


def _path(name: str) -> str:
    return os.path.join(TEMPLATES_DIR, f"{_safe(name)}.zpl")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def list_templates() -> list:
    """Return a sorted list of template names (without extension)."""
    names = []
    for filename in os.listdir(TEMPLATES_DIR):
        if filename.endswith(".zpl"):
            names.append(filename[:-4])
    return sorted(names)


def get_template(name: str) -> str | None:
    """Return the raw ZPL string for *name*, or *None* if it does not exist."""
    path = _path(name)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def save_template(name: str, content: str) -> None:
    """Persist *content* as the template named *name*."""
    path = _path(name)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)


def delete_template(name: str) -> bool:
    """Delete the template *name*.  Returns *True* if removed."""
    path = _path(name)
    if os.path.exists(path):
        os.remove(path)
        return True
    return False
