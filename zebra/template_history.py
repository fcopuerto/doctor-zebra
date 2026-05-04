"""Per-template version history.

Every time a template's ZPL or its sidecar JSON is about to change, we
snapshot the current contents into a ``.versions/<stem>/<timestamp>/``
directory next to the templates. Restoring a version takes one more
snapshot (of whatever was live before) so the user can always undo a
restore.

Layout::

    profiles/<profile>/templates_zpl/
      ETIQUETA_MEDIANA.zpl
      ETIQUETA_MEDIANA.zpl.json
      .versions/
        ETIQUETA_MEDIANA/
          20260504T112345Z/
            template.zpl
            sidecar.json   (optional — only if there was one)
            meta.json      ({"reason": "edit"} or {"reason": "restore"})

The directory is hidden (``.versions``) so casual users browsing the
profile folder don't see it. It's not pruned automatically — files are
small enough that even years of edits won't be a problem in practice.
"""

from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path

VERSIONS_DIRNAME = '.versions'
TIMESTAMP_FMT = '%Y%m%dT%H%M%SZ'


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def _versions_root(template_path: Path) -> Path:
    """``.versions/<stem>/`` next to the .zpl file."""
    return template_path.parent / VERSIONS_DIRNAME / template_path.stem


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime(TIMESTAMP_FMT)


def _sidecar_path(template_path: Path) -> Path:
    return template_path.with_suffix(template_path.suffix + '.json')


# ---------------------------------------------------------------------------
# Snapshot
# ---------------------------------------------------------------------------

def snapshot(template_path: Path, reason: str = 'edit') -> str | None:
    """Save the current state of ``template_path`` (+ sidecar if present).

    Returns the timestamp of the new snapshot, or ``None`` if there was
    nothing to snapshot (template doesn't exist yet, e.g. brand-new).
    Idempotent: two snapshots in the same second land in the same dir
    and the second silently overwrites the first.
    """
    if not template_path.is_file():
        return None
    try:
        ts = _utc_stamp()
        dest = _versions_root(template_path) / ts
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copy2(template_path, dest / 'template.zpl')

        sc = _sidecar_path(template_path)
        if sc.is_file():
            shutil.copy2(sc, dest / 'sidecar.json')

        meta = {
            'reason':       reason,
            'snapshot_at':  datetime.now(timezone.utc).isoformat(),
            'source':       template_path.name,
        }
        (dest / 'meta.json').write_text(
            json.dumps(meta, indent=2) + '\n', encoding='utf-8',
        )
        return ts
    except OSError as e:
        logging.warning(f'Could not snapshot {template_path.name}: {e}')
        return None


# ---------------------------------------------------------------------------
# List / read
# ---------------------------------------------------------------------------

def list_versions(template_path: Path) -> list[dict]:
    """Return ``[{timestamp, has_sidecar, size_bytes, reason, ts_human}, ...]``
    sorted newest first."""
    root = _versions_root(template_path)
    if not root.is_dir():
        return []
    out: list[dict] = []
    for entry in sorted(root.iterdir(), reverse=True):
        if not entry.is_dir():
            continue
        zpl = entry / 'template.zpl'
        if not zpl.is_file():
            continue
        sc = entry / 'sidecar.json'
        meta_path = entry / 'meta.json'
        meta: dict = {}
        if meta_path.is_file():
            try:
                meta = json.loads(meta_path.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                meta = {}
        out.append({
            'timestamp':  entry.name,
            'has_sidecar': sc.is_file(),
            'size_bytes': zpl.stat().st_size,
            'reason':     meta.get('reason', ''),
            'ts_human':   _human_ts(entry.name),
        })
    return out


def get_version(template_path: Path, timestamp: str) -> dict | None:
    """Return ``{zpl, sidecar, meta}`` for one version, or ``None``."""
    if not _is_valid_ts(timestamp):
        return None
    entry = _versions_root(template_path) / timestamp
    zpl = entry / 'template.zpl'
    if not zpl.is_file():
        return None
    payload: dict = {
        'timestamp': timestamp,
        'zpl':       zpl.read_text(encoding='utf-8'),
        'sidecar':   None,
        'meta':      {},
    }
    sc = entry / 'sidecar.json'
    if sc.is_file():
        try:
            payload['sidecar'] = sc.read_text(encoding='utf-8')
        except OSError:
            pass
    meta = entry / 'meta.json'
    if meta.is_file():
        try:
            payload['meta'] = json.loads(meta.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            pass
    return payload


# ---------------------------------------------------------------------------
# Restore
# ---------------------------------------------------------------------------

def restore_version(template_path: Path, timestamp: str) -> bool:
    """Restore a saved version, snapshotting the current state first.

    Returns True if the restore happened.
    """
    data = get_version(template_path, timestamp)
    if data is None:
        return False
    # Snapshot what's live so the user can roll the restore back too.
    snapshot(template_path, reason='restore')
    try:
        template_path.write_text(data['zpl'], encoding='utf-8')
        sc_path = _sidecar_path(template_path)
        if data['sidecar'] is not None:
            sc_path.write_text(data['sidecar'], encoding='utf-8')
        else:
            # Old version had no sidecar → drop the current one for parity.
            if sc_path.is_file():
                sc_path.unlink()
        return True
    except OSError as e:
        logging.warning(f'Restore failed for {template_path.name}@{timestamp}: {e}')
        return False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_valid_ts(s: str) -> bool:
    try:
        datetime.strptime(s, TIMESTAMP_FMT)
        return True
    except (TypeError, ValueError):
        return False


def _human_ts(s: str) -> str:
    """Convert ``20260504T112345Z`` to ``2026-05-04 11:23:45 UTC`` for the UI."""
    try:
        dt = datetime.strptime(s, TIMESTAMP_FMT).replace(tzinfo=timezone.utc)
        return dt.strftime('%Y-%m-%d %H:%M:%S UTC')
    except (TypeError, ValueError):
        return s
