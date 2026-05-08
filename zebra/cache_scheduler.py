"""Background auto-sync for the lookup cache.

Three trigger points keep the cache fresh without user intervention:

1. **App startup** — a daemon thread enumerates every configured
   ``(connection, table)`` pair (across all template sidecars) and syncs
   them in sequence. After the first pass it loops every
   :data:`CACHE_SYNC_INTERVAL` seconds.

2. **After a sidecar save** — :func:`maybe_sync_after_save` is called
   from the fields-editor POST handler so newly configured lookups have
   data ready by the time the user reaches the print form.

3. **Manual** — the "Sync now" button in the fields editor still works
   as a recovery tool when the SQL Server is reachable for the first
   time after a network outage.

If the data source is unreachable the sync logs the failure and moves
on; the previous cache (if any) keeps the print form working.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone

from zebra import datasources, fields as fields_mod, lookup_cache, zpl
from zebra.datasources.base import DataSourceError


CACHE_SYNC_INTERVAL = 30 * 60  # seconds — periodic refresh
_INITIAL_DELAY = 2             # let the app finish booting before first sync


_state_lock = threading.Lock()
_state: dict = {
    'thread': None,
    'last_run': None,
    'last_summary': None,
    'in_progress': set(),
    # Per-pair history: {(conn, table): {at, error}} — kept separate so a
    # successful sync clears the failure record and vice-versa.
    'last_success': {},
    'last_failure': {},
}


def get_status() -> dict:
    """Snapshot of the current scheduler state for the UI."""
    with _state_lock:
        return {
            'last_run': _state['last_run'],
            'last_summary': _state['last_summary'],
            'in_progress': sorted(list(_state['in_progress'])),
        }


def get_pair_status(connection: str, table: str) -> dict:
    """Last sync outcome for one (connection, table).

    Returns ``{last_success, last_failure, in_progress}`` where the success
    and failure entries are ``{at, error?}`` dicts (or None).
    """
    key = (connection, table)
    with _state_lock:
        return {
            'last_success': _state['last_success'].get(key),
            'last_failure': _state['last_failure'].get(key),
            'in_progress': key in _state['in_progress'],
        }


def collect_pairs(settings) -> set[tuple[str, str]]:
    """Walk every template's sidecar and return unique (connection, table) pairs."""
    pairs: set[tuple[str, str]] = set()
    templates_dir = settings.templates_dir
    for tpl in zpl.list_templates(templates_dir):
        path = templates_dir / tpl
        for spec in fields_mod.load_fields(path):
            if spec.type == 'lookup' and spec.source and spec.table:
                pairs.add((spec.source, spec.table))
    return pairs


def sync_one(app, connection_name: str, table: str) -> bool:
    """Sync one pair. Logs on failure, returns True on success."""
    settings = app.config['SETTINGS']
    cfg = datasources.get_connection(settings, connection_name)
    if not cfg:
        logging.info(f'Auto-sync skip: unknown connection {connection_name!r}')
        return False
    db_path = app.config['DB_PATH']
    key = (connection_name, table)

    with _state_lock:
        if key in _state['in_progress']:
            return False
        _state['in_progress'].add(key)

    try:
        password = settings.get_connection_password(connection_name)
        ds = datasources.build_datasource(cfg, password=password)
        result = lookup_cache.sync_table(db_path, ds, table)
        logging.info(
            f'Auto-sync {connection_name}/{table}: {result["row_count"]} rows'
        )
        record_outcome(key, ok=True)
        return True
    except DataSourceError as e:
        logging.warning(f'Auto-sync {connection_name}/{table} failed: {e}')
        record_outcome(key, ok=False, error=str(e))
        return False
    except Exception as e:  # defensive — never let a bad row crash the loop
        logging.exception(f'Auto-sync {connection_name}/{table} crashed: {e}')
        record_outcome(key, ok=False, error=str(e) or e.__class__.__name__)
        return False
    finally:
        with _state_lock:
            _state['in_progress'].discard(key)


def record_outcome(key: tuple, ok: bool, error: str = '') -> None:
    """Persist the sync result for a pair so the UI can render its state."""
    now = datetime.now(timezone.utc).isoformat(timespec='seconds')
    with _state_lock:
        if ok:
            _state['last_success'][key] = {'at': now}
            _state['last_failure'].pop(key, None)
        else:
            _state['last_failure'][key] = {'at': now, 'error': error}


def sync_all(app) -> dict:
    """Sync every configured pair once. Used by the loop and on demand."""
    settings = app.config['SETTINGS']
    settings.reload()
    pairs = collect_pairs(settings)
    ok = fail = 0
    for conn, table in pairs:
        if sync_one(app, conn, table):
            ok += 1
        else:
            fail += 1
    summary = {
        'ok': ok,
        'fail': fail,
        'total': len(pairs),
        'ran_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
    }
    with _state_lock:
        _state['last_run'] = summary['ran_at']
        _state['last_summary'] = summary
    return summary


def start_scheduler(app) -> None:
    """Launch the background thread. Idempotent.

    Flask's debug auto-reload spawns the app twice; the dedup check
    keeps us from running two threads in parallel.
    """
    with _state_lock:
        existing = _state.get('thread')
        if existing is not None and existing.is_alive():
            return

    def loop():
        time.sleep(_INITIAL_DELAY)
        while True:
            try:
                with app.app_context():
                    sync_all(app)
            except Exception:
                logging.exception('Cache auto-sync iteration crashed')
            time.sleep(CACHE_SYNC_INTERVAL)

    t = threading.Thread(target=loop, name='cache-auto-sync', daemon=True)
    with _state_lock:
        _state['thread'] = t
    t.start()
    logging.info('Cache auto-sync thread started')


def maybe_sync_after_save(app, specs) -> None:
    """Schedule a background sync for any lookup pair in ``specs``.

    Runs in a daemon thread so the HTTP response isn't held up. Pairs
    already configured in another template are still re-synced — cheap
    if cache is current, useful if that table changed upstream.
    """
    pairs = {
        (s.source, s.table) for s in specs
        if getattr(s, 'type', '') == 'lookup' and s.source and s.table
    }
    if not pairs:
        return

    def go():
        with app.app_context():
            for conn, table in pairs:
                sync_one(app, conn, table)

    threading.Thread(
        target=go, name='cache-after-save', daemon=True,
    ).start()
