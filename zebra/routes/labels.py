"""Routes for printing, previewing, and browsing labels."""

import logging
import os
from pathlib import Path

from flask import (
    Blueprint, current_app, jsonify, redirect, render_template, request, url_for,
)

from zebra import (
    cache_scheduler, datasources, db, fields as fields_mod, lookup_cache,
    preview, zpl,
)
from zebra.constants import MAX_COPIES
from zebra.datasources.base import DataSourceError
from zebra.printer import PrinterError, send_to_printer

bp = Blueprint('labels', __name__)


def _settings():
    return current_app.config['SETTINGS']


def _db_path() -> str:
    return current_app.config['DB_PATH']


def _resolve(template_file: str) -> Path | None:
    return zpl.resolve_template(_settings().templates_dir, template_file)


def _specs_for(template_file: str) -> list[fields_mod.FieldSpec]:
    path = _resolve(template_file)
    if path is None:
        return []
    return fields_mod.load_fields(path)


def _render_form(template_file: str = '', values: dict | None = None,
                 image_url: str | None = None):
    templates_dir = _settings().templates_dir
    templates = zpl.list_templates(templates_dir)
    if not template_file and templates:
        template_file = templates[0]

    specs = _specs_for(template_file) if template_file else []

    # Legacy rows (or missing templates) may carry values with no corresponding
    # spec — synthesise plain specs so the form still shows them.
    if values:
        known = {s.key for s in specs}
        for key in values.keys():
            if key not in known:
                specs.append(fields_mod.FieldSpec(key=key))

    defaults = fields_mod.specs_to_defaults(specs)
    merged = {**defaults, **(values or {})}

    return render_template(
        'form.html',
        templates=templates,
        template_file=template_file,
        template_fields=specs,
        field_values=merged,
        image_url=image_url,
    )


@bp.route('/')
def index():
    if not _settings().default_printer:
        return redirect(url_for('config.wizard'))
    latest = db.most_recent(_db_path())
    if latest:
        template_file, values = latest
        return _render_form(template_file=template_file, values=values)
    return _render_form()


@bp.route('/load/<label_id>')
def load_label(label_id):
    record = db.get_by_id(_db_path(), label_id)
    if record:
        template_file, values = record
        return _render_form(template_file=template_file, values=values)
    return _render_form()


@bp.route('/api/lookup/<path:template_file>/<field_key>')
def api_lookup(template_file, field_key):
    """Search a lookup field against the local cache.

    The cache is populated by ``POST /api/connections/<name>/sync_table``;
    this endpoint never hits SQL Server live, so the print form keeps
    working when the database is unreachable.

    Returns ``{rows, value_column, autofill, display_columns, cache: {...}}``
    where ``cache`` describes the freshness of the local data.
    """
    path = _resolve(template_file)
    if path is None:
        return jsonify({'error': 'Invalid template'}), 404
    specs = fields_mod.load_fields(path)
    spec = next((s for s in specs if s.key == field_key), None)
    if spec is None or spec.type != 'lookup':
        return jsonify({'error': 'Not a lookup field'}), 404

    meta = lookup_cache.get_meta(_db_path(), spec.source, spec.table)
    cache_info = {
        'last_sync': meta['last_sync'] if meta else None,
        'row_count': meta['row_count'] if meta else 0,
    }

    q = (request.args.get('q') or '').strip()
    if not q:
        return jsonify({
            'rows': [],
            'value_column': spec.value_column,
            'autofill': spec.autofill,
            'display_columns': spec.display_columns or spec.search_columns,
            'cache': cache_info,
        })

    if not meta:
        # Auto-sync should normally have populated this on startup.
        # If we still have no meta, kick a one-shot background sync and
        # tell the user to retry in a moment.
        status = cache_scheduler.get_status()
        already_running = [spec.source, spec.table] in status.get('in_progress', [])
        if not already_running:
            import threading
            threading.Thread(
                target=cache_scheduler.sync_one,
                args=(current_app._get_current_object(), spec.source, spec.table),
                daemon=True,
            ).start()
        return jsonify({
            'rows': [],
            'value_column': spec.value_column,
            'autofill': spec.autofill,
            'display_columns': spec.display_columns or spec.search_columns,
            'cache': cache_info,
            'warning': (
                'Cache is being prepared in the background — retry in a few seconds.'
                if already_running else
                'Cache is being prepared now. Retry in a few seconds.'
            ),
            'syncing': True,
        })

    return_cols = list(dict.fromkeys(
        list(spec.display_columns or [])
        + ([spec.value_column] if spec.value_column else [])
        + list(spec.autofill.values())
    )) or list(spec.search_columns)

    rows = lookup_cache.search(
        _db_path(), spec.source, spec.table,
        spec.search_columns, q,
        return_columns=return_cols, limit=25,
    )
    safe_rows = [{k: _safe(v) for k, v in row.items()} for row in rows]
    return jsonify({
        'rows': safe_rows,
        'display_columns': spec.display_columns or spec.search_columns,
        'value_column': spec.value_column,
        'autofill': spec.autofill,
        'cache': cache_info,
    })


def _safe(v):
    if v is None or isinstance(v, (str, int, float, bool)):
        return v
    return str(v)


@bp.route('/api/fields/<path:template_file>')
def api_fields(template_file):
    """Return the field spec for a template (for dynamic form rendering)."""
    path = _resolve(template_file)
    if path is None:
        return jsonify({'error': 'Invalid template'}), 404
    specs = fields_mod.load_fields(path)
    return jsonify({
        'template_file': template_file,
        'fields': [s.to_dict() for s in specs],
    })


@bp.route('/api/preview/raw', methods=['POST'])
def preview_raw():
    """Render arbitrary ZPL (raw text body or 'zpl' form field) to PNG.

    Used by the source editor for live preview. Doesn't go through the
    template sidecar — what you POST is what Labelary sees.
    """
    zpl_text = (request.get_data(as_text=True) or '').strip()
    if not zpl_text:
        zpl_text = (request.form.get('zpl') or '').strip()
    if not zpl_text:
        return jsonify({'error': 'Empty ZPL'}), 400

    png = preview.zpl_to_png(zpl_text)
    if not png:
        return jsonify({'error': 'Preview service unavailable. Check your internet '
                        'connection — Labelary is rendered remotely.'}), 502

    static_dir = Path(current_app.static_folder)
    (static_dir / 'preview_raw.png').write_bytes(png)
    image_url = url_for('static', filename='preview_raw.png') + f'?t={os.urandom(4).hex()}'
    return jsonify({'image_url': image_url})


@bp.route('/preview', methods=['POST'])
def preview_label():
    template_file = request.form.get('template_file', '')
    path = _resolve(template_file)
    if path is None:
        return jsonify({'error': 'Invalid template'}), 400

    specs = fields_mod.load_fields(path)
    values = fields_mod.sanitize_values(specs, request.form)

    png = preview.zpl_to_png(zpl.render(path, values))
    if not png:
        return jsonify({'image_url': None, 'error': 'Preview service unavailable'}), 502

    static_dir = Path(current_app.static_folder)
    (static_dir / 'preview.png').write_bytes(png)
    image_url = url_for('static', filename='preview.png') + f'?t={os.urandom(4).hex()}'
    return jsonify({'image_url': image_url})


@bp.route('/generate', methods=['POST'])
def generate_zpl():
    template_file = request.form.get('template_file', '')
    path = _resolve(template_file)
    if path is None:
        return jsonify({'message': 'Invalid template'}), 400

    try:
        copies = max(1, min(MAX_COPIES, int(request.form.get('copies', 1))))
    except (TypeError, ValueError):
        copies = 1

    specs = fields_mod.load_fields(path)
    values = fields_mod.sanitize_values(specs, request.form)

    # Required-field validation
    missing = [s.label or s.key for s in specs if s.required and not values.get(s.key)]
    if missing:
        return jsonify({'message': f'Missing required fields: {", ".join(missing)}'}), 400

    rendered = zpl.render(path, values)
    printer_name = _settings().printer_for_template(template_file)

    try:
        send_to_printer(printer_name, rendered, copies)
    except PrinterError as e:
        logging.error(f"Failed to send label to printer: {e}")
        return jsonify({'message': f'Failed to send label to printer: {e}'}), 500

    logging.info(
        f"Label sent to printer {printer_name} using template {template_file} "
        f"({copies} copies)"
    )
    db.insert(_db_path(), template_file, values)
    return jsonify({'message': 'Label sent to printer successfully!'})


@bp.route('/history')
def history():
    records = db.list_all(_db_path())
    return render_template('history.html', records=records)
