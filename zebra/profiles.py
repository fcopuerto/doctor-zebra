"""Multi-profile support: each profile is a self-contained directory.

Layout::

    profiles/
        .active                    ← plain text, holds the active profile name
        default/
            config.cfg
            secrets.cfg
            labels.db
            templates_zpl/
        cliente_x/
            …

Switching profiles is *restart-based*. Settings, DB handles and the cache
scheduler are bound to paths at :func:`create_app` time; rebinding them on
the fly is too risky for a desktop install. The UI writes the new active
profile to ``.active`` and asks the user to relaunch.

On first run :func:`bootstrap` creates ``profiles/default/`` and moves any
existing root-level ``config.cfg`` / ``secrets.cfg`` / ``labels.db`` /
``templates_zpl`` inside it so the user keeps every byte they had.
"""

from __future__ import annotations

import logging
import re
import shutil
from pathlib import Path

PROFILES_DIRNAME = 'profiles'
ACTIVE_FILENAME = '.active'
DEFAULT_PROFILE = 'default'

_NAME_RE = re.compile(r'^[a-zA-Z][a-zA-Z0-9_\-]{0,30}$')


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def _profiles_root(base_dir: Path) -> Path:
    return Path(base_dir) / PROFILES_DIRNAME


def _active_file(base_dir: Path) -> Path:
    return _profiles_root(base_dir) / ACTIVE_FILENAME


def profile_dir(base_dir: Path, name: str) -> Path:
    return _profiles_root(base_dir) / name


def is_valid_name(name: str) -> bool:
    return bool(_NAME_RE.match(name or ''))


# ---------------------------------------------------------------------------
# Bootstrap (first-run migration)
# ---------------------------------------------------------------------------

def bootstrap(base_dir: Path) -> Path:
    """Ensure profiles/ exists and ``default`` is populated.

    On first run, moves existing ``config.cfg`` / ``secrets.cfg`` /
    ``labels.db`` / ``templates_zpl`` from ``base_dir`` into
    ``profiles/default/`` so the user's data survives the upgrade.
    Idempotent: subsequent calls return the active directory without
    touching anything.
    """
    base_dir = Path(base_dir)
    root = _profiles_root(base_dir)
    if root.exists():
        return _active_dir(base_dir)

    root.mkdir(parents=True, exist_ok=True)
    default_dir = root / DEFAULT_PROFILE
    default_dir.mkdir(exist_ok=True)

    moved = []
    for filename in ('config.cfg', 'secrets.cfg', 'labels.db'):
        src = base_dir / filename
        if src.exists() and src.is_file():
            shutil.move(str(src), str(default_dir / filename))
            moved.append(filename)

    src_templates = base_dir / 'templates_zpl'
    dst_templates = default_dir / 'templates_zpl'
    if src_templates.exists() and src_templates.is_dir():
        shutil.move(str(src_templates), str(dst_templates))
        moved.append('templates_zpl/')
    else:
        dst_templates.mkdir(exist_ok=True)

    # Make sure config.cfg has a templates_dir pointing inside the profile.
    cfg_path = default_dir / 'config.cfg'
    if not cfg_path.exists():
        cfg_path.write_text(
            '[settings]\ntemplates_dir = templates_zpl\n',
            encoding='utf-8',
        )

    set_active(base_dir, DEFAULT_PROFILE)
    if moved:
        logging.info(
            f'Profiles bootstrap: moved {", ".join(moved)} into profiles/{DEFAULT_PROFILE}/'
        )
    else:
        logging.info(f'Profiles bootstrap: created empty profiles/{DEFAULT_PROFILE}/')
    return default_dir


# ---------------------------------------------------------------------------
# Active profile
# ---------------------------------------------------------------------------

def active_name(base_dir: Path) -> str:
    """Return the active profile name, falling back to ``default``."""
    f = _active_file(base_dir)
    if f.is_file():
        name = f.read_text(encoding='utf-8').strip()
        if is_valid_name(name):
            return name
    return DEFAULT_PROFILE


def _active_dir(base_dir: Path) -> Path:
    return profile_dir(base_dir, active_name(base_dir))


def set_active(base_dir: Path, name: str) -> None:
    if not is_valid_name(name):
        raise ValueError(f'Invalid profile name: {name!r}')
    if not profile_dir(base_dir, name).is_dir():
        raise ValueError(f'Profile {name!r} does not exist')
    _active_file(base_dir).write_text(name + '\n', encoding='utf-8')


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def list_profiles(base_dir: Path) -> list[str]:
    root = _profiles_root(base_dir)
    if not root.is_dir():
        return []
    return sorted(
        p.name for p in root.iterdir()
        if p.is_dir() and not p.name.startswith('.')
    )


def create_profile(base_dir: Path, name: str) -> Path:
    if not is_valid_name(name):
        raise ValueError(
            'Profile name must start with a letter and contain only '
            'letters, digits, underscore or dash (max 31 chars).'
        )
    target = profile_dir(base_dir, name)
    if target.exists():
        raise FileExistsError(f'Profile {name!r} already exists')
    target.mkdir(parents=True)
    (target / 'templates_zpl').mkdir()
    (target / 'config.cfg').write_text(
        '[settings]\ntemplates_dir = templates_zpl\n',
        encoding='utf-8',
    )
    logging.info(f'Created profile {name!r} at {target}')
    return target


def delete_profile(base_dir: Path, name: str) -> None:
    if name == active_name(base_dir):
        raise ValueError(
            'Cannot delete the active profile. Switch to another first.'
        )
    target = profile_dir(base_dir, name)
    if not target.is_dir():
        raise FileNotFoundError(f'Profile {name!r} not found')
    shutil.rmtree(target)
    logging.info(f'Deleted profile {name!r}')


# ---------------------------------------------------------------------------
# Path resolver used by create_app
# ---------------------------------------------------------------------------

def resolve_paths(base_dir: Path) -> dict:
    """Return the paths to use for the currently active profile."""
    active = _active_dir(base_dir)
    return {
        'profile_name': active_name(base_dir),
        'profile_dir': active,
        'config_path': active / 'config.cfg',
        'db_path': active / 'labels.db',
        'templates_dir': active / 'templates_zpl',
    }
