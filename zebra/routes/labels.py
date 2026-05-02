"""Routes for printing, previewing, and browsing labels."""

import logging
import os
from pathlib import Path

from flask import (
    Blueprint, current_app, jsonify, redirect, render_template, request, url_for,
)

from zebra import (
    LANG_COOKIE, cache_scheduler, datasources, db, fields as fields_mod,
    i18n, lookup_cache, preview, zpl,
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
    rendered = zpl.inject_print_settings(rendered, fields_mod.load_print_settings(path))
    printer_name = _settings().printer_for_template(template_file)
    width_mm, height_mm = zpl.label_dimensions_mm(rendered)
    profile_name = current_app.config.get('PROFILE_NAME')

    # Capture the value of the first lookup field so the dashboard can rank
    # the most-printed items (typically a SKU). Templates with no lookup
    # field, or with the field left blank, simply record None.
    lookup_key: str | None = None
    for s in specs:
        if s.type == 'lookup':
            v = (values.get(s.key) or '').strip()
            if v:
                lookup_key = v
            break

    try:
        send_to_printer(printer_name, rendered, copies)
    except PrinterError as e:
        logging.error(f"Failed to send label to printer: {e}")
        # Still record the failed attempt so the dashboard can surface it.
        db.insert(
            _db_path(), template_file, values,
            copies=copies, printer_name=printer_name,
            status='error', error_message=str(e),
            label_width_mm=width_mm, label_height_mm=height_mm,
            lookup_key=lookup_key, profile_name=profile_name,
        )
        return jsonify({'message': f'Failed to send label to printer: {e}'}), 500

    logging.info(
        f"Label sent to printer {printer_name} using template {template_file} "
        f"({copies} copies)"
    )
    db.insert(
        _db_path(), template_file, values,
        copies=copies, printer_name=printer_name,
        status='ok',
        label_width_mm=width_mm, label_height_mm=height_mm,
        lookup_key=lookup_key, profile_name=profile_name,
    )
    return jsonify({'message': 'Label sent to printer successfully!'})


@bp.route('/history')
def history():
    records = db.list_all(_db_path())
    return render_template('history.html', records=records)


@bp.route('/api/lang/<code>', methods=['POST'])
def set_lang(code):
    """Persist the user's language choice in a cookie + lang.txt.

    The cookie is what the running Flask process reads on every request.
    lang.txt lives in BASE_DIR (~/.comandante_zebra/) so the splash screen —
    which renders before Flask is reachable — can pick the right
    catalogue at the next launch.
    """
    if not i18n.is_supported(code):
        return jsonify({'ok': False, 'error': 'unsupported language'}), 400
    code = code.lower()

    # Best-effort write of the persistent language hint. We deliberately
    # swallow OSError (read-only volumes, antivirus interference, etc.) —
    # the cookie still works for the running session.
    try:
        (Path(current_app.config['BASE_DIR']) / 'lang.txt').write_text(
            code + '\n', encoding='utf-8',
        )
    except OSError as e:
        logging.warning(f'Could not persist lang.txt: {e}')

    resp = jsonify({'ok': True, 'lang': code})
    resp.set_cookie(
        LANG_COOKIE, code,
        max_age=60 * 60 * 24 * 365,
        samesite='Lax',
        httponly=False,
    )
    return resp


@bp.route('/dashboard')
def dashboard():
    """Operational overview: KPIs, top templates/sizes/printers, errors."""
    p = _db_path()
    activity = db.daily_activity(p, days=30)
    return render_template(
        'dashboard.html',
        kpis=db.kpi_counts(p),
        activity=activity,
        activity_chart=_activity_chart_svg(activity),
        top_templates=db.top_templates(p, limit=5),
        top_sizes=db.top_sizes(p, limit=5),
        top_printers=db.top_printers(p, limit=5),
        top_items=db.top_items(p, limit=10),
        recent_errors=db.recent_errors(p, limit=8),
    )


def _activity_chart_svg(activity: list[dict]) -> str:
    """Return inline SVG markup for a 30-day bar chart.

    Empty days still render a 1px tick so the axis density is obvious.
    """
    if not activity:
        return ''
    n = len(activity)
    width = 600
    height = 110
    pad_top = 8
    pad_bottom = 18  # room for the start/end date labels
    chart_h = height - pad_top - pad_bottom
    bar_gap = 2
    bar_w = max(2, (width - bar_gap * (n - 1)) / n)
    max_count = max((d['count'] for d in activity), default=0) or 1

    bars: list[str] = []
    for i, d in enumerate(activity):
        x = i * (bar_w + bar_gap)
        h = max(1, (d['count'] / max_count) * chart_h)
        y = pad_top + (chart_h - h)
        bars.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{h:.1f}" '
            f'rx="1.5" class="bar"><title>{d["date"]}: {d["count"]}</title></rect>'
        )

    first = activity[0]['date']
    last = activity[-1]['date']
    return (
        f'<svg viewBox="0 0 {width} {height}" preserveAspectRatio="none" '
        f'class="activity-chart" role="img" aria-label="Activity over the last {n} days">'
        f'<g>{"".join(bars)}</g>'
        f'<text x="0" y="{height - 4}" class="activity-chart__axis">{first}</text>'
        f'<text x="{width}" y="{height - 4}" text-anchor="end" '
        f'class="activity-chart__axis">{last}</text>'
        f'</svg>'
    )
