"""
Profile management.

Each profile is stored as a JSON file inside ``data/profiles/``.  A profile
bundles printer connection settings, a reference to a ZPL template, and the
field definitions shown on the print form.

Profile schema::

    {
        "name": "My Profile",
        "printer": {
            "host": "192.168.1.100",
            "port": 9100
        },
        "template": "etiqueta_producto",
        "fields": [
            {
                "name": "codigo",
                "label": "Código",
                "type": "text",
                "required": true,
                "lookup": "productos",          # optional – lookup name
                "lookup_value_field": "code",   # optional
                "lookup_label_field": "name",   # optional
                "autofill": [                   # optional
                    {"from": "descripcion", "to": "descripcion"}
                ]
            }
        ]
    }
"""
import json
import os
import re

from config import PROFILES_DIR

os.makedirs(PROFILES_DIR, exist_ok=True)

_SAFE_NAME = re.compile(r"^[A-Za-z0-9_\-]+$")


def _safe(name: str) -> str:
    """Raise ValueError if *name* contains unsafe characters."""
    if not _SAFE_NAME.match(name):
        raise ValueError(f"Invalid profile name: {name!r}")
    return name


def _path(name: str) -> str:
    return os.path.join(PROFILES_DIR, f"{_safe(name)}.json")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def list_profiles() -> list:
    """Return a sorted list of profile names (without extension)."""
    names = []
    for filename in os.listdir(PROFILES_DIR):
        if filename.endswith(".json"):
            names.append(filename[:-5])
    return sorted(names)


def get_profile(name: str) -> dict | None:
    """Return the profile dict for *name*, or *None* if it does not exist."""
    path = _path(name)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def save_profile(name: str, data: dict) -> None:
    """Persist *data* as the profile named *name*.

    Creates or overwrites the file.
    """
    path = _path(name)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)


def delete_profile(name: str) -> bool:
    """Delete the profile *name*.  Returns *True* if the file was removed,
    *False* if it did not exist.
    """
    path = _path(name)
    if os.path.exists(path):
        os.remove(path)
        return True
    return False
