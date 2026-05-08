"""Routes for printing, previewing, and browsing labels."""

import logging
import os
from pathlib import Path

from flask import (
    Blueprint, current_app, jsonify, redirect, render_template, request, url_for,
)

from zebra import (
    LANG_COOKIE, cache_scheduler, datasources, db, fields as fields_mod,
    i18n, lookup_cache, preview, template_history, updater, zpl,
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

    # Lookup fields are meant to be searched, not pre-filled from history:
    # showing an old SKU paired with description/barcode that the user
    # didn't reconfirm leads to mis-prints. Reset both the lookup field
    # itself and every field it would autofill, so the user has to pick
    # a row (or override manually after picking).
    if values:
        reset_keys: set[str] = set()
        for s in specs:
            if s.type == 'lookup':
                reset_keys.add(s.key)
                reset_keys.update((s.autofill or {}).keys())
        for key in reset_keys:
            merged[key] = defaults.get(key, '')

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
    """Search a lookup field, cache-first with a live DB fallback.

    Behaviour:
      1. Search the local SQLite cache (offline-first, instant).
      2. If the cache returns 0 rows AND we have a working connection
         config, fall through to a live ``DataSource.search()`` call so
         users find recently-added records without waiting for the next
         scheduled sync.
      3. If the live attempt fails the failure is recorded so the offline
         badge appears in the UI; the cache results (empty in this case)
         are returned.

    Returns ``{rows, value_column, autofill, display_columns, cache,
    live?}`` — ``live`` is set when results came straight from the DB.
    """
    path = _resolve(template_file)
    if path is None:
        return jsonify({'error': 'Invalid template'}), 404
    specs = fields_mod.load_fields(path)
    spec = next((s for s in specs if s.key == field_key), None)
    if spec is None or spec.type != 'lookup':
        return jsonify({'error': 'Not a lookup field'}), 404

    meta = lookup_cache.get_meta(_db_path(), spec.source, spec.table)

    def _build_cache_info():
        """Snapshot of cache + connection state (re-read after each attempt)."""
        ps = cache_scheduler.get_pair_status(spec.source, spec.table)
        return {
            'last_sync': meta['last_sync'] if meta else None,
            'row_count': meta['row_count'] if meta else 0,
            # connection_status:
            #   'live'    → most recent attempt succeeded
            #   'offline' → most recent attempt failed
            #   'unknown' → no sync attempt has finished yet
            'connection_status': _classify_connection(ps),
            'last_failure': ps['last_failure'],
            'syncing_now': ps['in_progress'],
        }

    q = (request.args.get('q') or '').strip()
    if not q:
        return jsonify({
            'rows': [],
            'value_column': spec.value_column,
            'autofill': spec.autofill,
            'display_columns': spec.display_columns or spec.search_columns,
            'cache': _build_cache_info(),
        })

    return_cols = list(dict.fromkeys(
        list(spec.display_columns or [])
        + ([spec.value_column] if spec.value_column else [])
        + list(spec.autofill.values())
    )) or list(spec.search_columns)

    # 1) Cache first — instant, works offline.
    rows = []
    if meta:
        rows = lookup_cache.search(
            _db_path(), spec.source, spec.table,
            spec.search_columns, q,
            return_columns=return_cols, limit=25,
        )

    # 2) Live fallback — runs when cache is empty (never synced) or when
    # the user's query didn't match anything cached. Catches the "added
    # an item after the last sync" case the user reported.
    live = False
    if not rows:
        live_rows = _try_live_search(spec, q, return_cols)
        if live_rows is not None:
            rows = live_rows
            live = True

    # 3) No rows + no live response: surface the right empty-state.
    if not rows and not live:
        pair_status = cache_scheduler.get_pair_status(spec.source, spec.table)
        if not meta:
            # Cache empty AND live unreachable: user can keep typing manually.
            if pair_status['last_failure'] and not pair_status['in_progress']:
                return jsonify({
                    'rows': [],
                    'value_column': spec.value_column,
                    'autofill': spec.autofill,
                    'display_columns': spec.display_columns or spec.search_columns,
                    'cache': _build_cache_info(),
                    'no_cache': True,
                })
            # Initial sync still pending: tell the UI to retry shortly.
            if not pair_status['in_progress']:
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
                'cache': _build_cache_info(),
                'syncing': True,
            })

    safe_rows = [{k: _safe(v) for k, v in row.items()} for row in rows]
    response = {
        'rows': safe_rows,
        'display_columns': spec.display_columns or spec.search_columns,
        'value_column': spec.value_column,
        'autofill': spec.autofill,
        'cache': _build_cache_info(),
    }
    if live:
        response['live'] = True
    return jsonify(response)


def _try_live_search(spec, query: str, return_cols: list) -> list | None:
    """Run a one-off live search against the data source.

    Returns the row list on success (possibly empty), or ``None`` if the
    backend isn't configured or the query failed. Failures are recorded
    in the cache scheduler so the UI can show the offline state.
    """
    settings = _settings()
    cfg = datasources.get_connection(settings, spec.source)
    if cfg is None:
        return None
    pair_key = (spec.source, spec.table)
    try:
        password = settings.get_connection_password(spec.source)
        ds = datasources.build_datasource(cfg, password=password)
        rows = ds.search(
            spec.table, spec.search_columns, query,
            return_columns=return_cols, limit=25,
        )
        cache_scheduler.record_outcome(pair_key, ok=True)
        return rows
    except DataSourceError as e:
        logging.info(f'Live lookup {spec.source}/{spec.table} failed: {e}')
        cache_scheduler.record_outcome(pair_key, ok=False, error=str(e))
        return None
    except Exception as e:  # defensive — never block a search on an obscure error
        logging.exception(f'Live lookup {spec.source}/{spec.table} crashed')
        cache_scheduler.record_outcome(
            pair_key, ok=False, error=str(e) or e.__class__.__name__,
        )
        return None


def _safe(v):
    if v is None or isinstance(v, (str, int, float, bool)):
        return v
    return str(v)


def _values_for_preview(specs, form) -> dict[str, str]:
    """Like ``sanitize_values`` but never produces an empty value.

    Used only for the preview path: when a field is empty in the form we
    fall back to its ``default``, and if that's empty too we render the
    placeholder token (``{key}``) literally so the user can see *where*
    each field will land on the label even before filling it in.
    """
    out: dict[str, str] = {}
    for s in specs:
        v = str(form.get(s.key) or '').strip()
        if not v:
            v = (s.default or '').strip()
        if not v:
            v = '{' + s.key + '}'
        out[s.key] = v
    return out


def _classify_connection(pair_status: dict) -> str:
    """Convert per-pair sync history into a single connection-state label.

    A failure that came after the last success means we lost connectivity;
    the opposite ordering means we recovered. With no history we can't say
    so we report 'unknown' and let the UI decide whether to bother the user.
    """
    success = pair_status.get('last_success') or {}
    failure = pair_status.get('last_failure') or {}
    s_at = success.get('at')
    f_at = failure.get('at')
    if not s_at and not f_at:
        return 'unknown'
    if f_at and (not s_at or f_at > s_at):
        return 'offline'
    return 'live'


@bp.route('/api/fields/<path:template_file>')
def api_fields(template_file):
    """Return the field spec + print settings for a template.

    Optional ``?version=<ts>`` reads the spec from the snapshot
    sidecar instead of the live one — used by the print form when
    the user picks an older version of a template to print.
    """
    path = _resolve(template_file)
    if path is None:
        return jsonify({'error': 'Invalid template'}), 404
    version = (request.args.get('version') or '').strip()

    if version and version != 'current':
        # Build specs from the snapshot's sidecar, falling back to
        # autodetect against the snapshot's ZPL if no sidecar was saved.
        snap = template_history.get_version(path, version)
        if snap is None:
            return jsonify({'error': 'Unknown version'}), 404
        sidecar_text = snap.get('sidecar')
        ps = {}
        if sidecar_text:
            try:
                import json as _json
                doc = _json.loads(sidecar_text)
                raw_fields = doc.get('fields') if isinstance(doc, dict) else None
                if isinstance(raw_fields, list):
                    specs = [fields_mod.FieldSpec.from_dict(f) for f in raw_fields]
                else:
                    specs = fields_mod.autodetect_from_zpl(snap['zpl'])
                ps = fields_mod._coerce_print_settings(
                    doc.get('print_settings') if isinstance(doc, dict) else None
                )
            except Exception:  # noqa: BLE001
                specs = fields_mod.autodetect_from_zpl(snap['zpl'])
        else:
            specs = fields_mod.autodetect_from_zpl(snap['zpl'])
        return jsonify({
            'template_file':  template_file,
            'fields':         [s.to_dict() for s in specs],
            'print_settings': ps,
            'version':        version,
        })

    specs = fields_mod.load_fields(path)
    return jsonify({
        'template_file':  template_file,
        'fields':         [s.to_dict() for s in specs],
        'print_settings': fields_mod.load_print_settings(path),
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
    values = _values_for_preview(specs, request.form)

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

    # Optional: print from a specific saved version of this template,
    # not the live file. Used by the version selector on /print.
    version_ts = (request.form.get('version_ts') or '').strip()

    if version_ts and version_ts != 'current':
        snap = template_history.get_version(path, version_ts)
        if snap is None:
            return jsonify({'message': 'Unknown template version'}), 400
        # Build specs from snapshot's sidecar (or autodetect from its ZPL).
        sidecar_text = snap.get('sidecar')
        if sidecar_text:
            try:
                import json as _json
                doc = _json.loads(sidecar_text)
                raw_fields = doc.get('fields') if isinstance(doc, dict) else None
                if isinstance(raw_fields, list):
                    specs = [fields_mod.FieldSpec.from_dict(f) for f in raw_fields]
                else:
                    specs = fields_mod.autodetect_from_zpl(snap['zpl'])
            except Exception:  # noqa: BLE001
                specs = fields_mod.autodetect_from_zpl(snap['zpl'])
        else:
            specs = fields_mod.autodetect_from_zpl(snap['zpl'])
        zpl_source = snap['zpl']
    else:
        specs = fields_mod.load_fields(path)
        zpl_source = None  # use live file via zpl.render below

    values = fields_mod.sanitize_values(specs, request.form)

    # Required-field validation
    missing = [s.label or s.key for s in specs if s.required and not values.get(s.key)]
    if missing:
        return jsonify({'message': f'Missing required fields: {", ".join(missing)}'}), 400

    if zpl_source is not None:
        rendered = zpl.render_text(zpl_source, values,
                                    label=f'{template_file}@{version_ts}')
    else:
        rendered = zpl.render(path, values)

    # Print settings: form overrides win over sidecar defaults. If the form
    # didn't include them at all we keep the template's defaults.
    template_ps = fields_mod.load_print_settings(path)
    has_form_ps = any(k in request.form for k in ('media_type', 'speed_ips', 'darkness'))
    if has_form_ps:
        ps = {
            'media_type': request.form.get('media_type', template_ps.get('media_type', '')),
            'speed_ips':  request.form.get('speed_ips',  template_ps.get('speed_ips',  0)),
            'darkness':   request.form.get('darkness',   template_ps.get('darkness',   -1)),
        }
    else:
        ps = template_ps
    rendered = zpl.inject_print_settings(rendered, ps)

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


@bp.route('/api/update/check')
def update_check():
    """Return current update status. Cached server-side; cheap to call."""
    from zebra import __version__
    force = request.args.get('force', '').lower() in ('1', 'true', 'yes')
    return jsonify(updater.check(__version__, force=force))


@bp.route('/api/update/dismiss', methods=['POST'])
def update_dismiss():
    """Tell the app to stop nagging about a specific version."""
    body = request.get_json(silent=True) or {}
    version = body.get('version') or ''
    if not version:
        return jsonify({'ok': False, 'error': 'version required'}), 400
    updater.dismiss(version)
    return jsonify({'ok': True, 'dismissed': version.lstrip('v')})


@bp.route('/healthz')
def healthz():
    """Liveness/readiness probe.

    Used by the splash window's _wait_until_ready loop and by anyone
    monitoring the app from outside (e.g. a sibling Comandante Zebra
    on the LAN that wants to know if we're up before talking to us).
    """
    import time
    from zebra import __version__
    started = current_app.config.get('STARTED_AT')
    uptime = max(0, int(time.time() - started)) if started else 0
    return jsonify({
        'ok':       True,
        'app':      'comandante_zebra',
        'version':  __version__,
        'profile':  current_app.config.get('PROFILE_NAME', ''),
        'uptime_s': uptime,
    })


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
