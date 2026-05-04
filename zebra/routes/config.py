"""Route for editing printer and per-template configuration from the UI."""

import logging
import re

from flask import (
    Blueprint, current_app, jsonify, redirect, render_template, request, url_for,
)

from pathlib import Path

from zebra import (
    cache_scheduler, datasources, fields as fields_mod, lookup_cache,
    printer, printer_tools, profiles, zpl,
)
from zebra.datasources.base import ConnectionConfig, DataSourceError

bp = Blueprint('config', __name__)


def _settings():
    return current_app.config['SETTINGS']


def _compose_target(form) -> str:
    """Build a ``printer_name`` target string from the builder fields."""
    backend = (form.get('backend') or '').strip().lower()

    if backend == 'system':
        name = (form.get('system_printer') or '').strip()
        if not name:
            return ''
        # Prefix so the chosen OS backend is unambiguous across machines.
        return f'win://{name}' if printer.IS_WINDOWS else f'cups://{name}'

    if backend == 'tcp':
        host = (form.get('tcp_host') or '').strip()
        port = (form.get('tcp_port') or '').strip() or '9100'
        if not host:
            return ''
        return f'{host}:{port}' if port != '9100' else host

    if backend == 'advanced':
        return (form.get('raw_target') or '').strip()

    return ''


def _decompose_target(target: str) -> dict:
    """Split a stored target back into builder fields for pre-filling the form."""
    fields = {
        'backend': 'system',
        'system_printer': '',
        'tcp_host': '',
        'tcp_port': '9100',
        'raw_target': target or '',
    }
    if not target:
        return fields

    backend, remainder = printer.parse_target(target)
    if backend == 'tcp':
        host, port = printer.split_host_port(remainder)
        fields.update(backend='tcp', tcp_host=host, tcp_port=str(port))
    elif backend in ('windows', 'cups'):
        fields.update(backend='system', system_printer=remainder)
    else:
        fields['backend'] = 'advanced'
    return fields


@bp.route('/config')
def config_page():
    """Settings hub — three tiles linking to themed sub-pages."""
    settings = _settings()
    settings.reload()

    status, color = printer.printer_status(settings.default_printer)
    templates_available = zpl.list_templates(settings.templates_dir)
    overrides_count = sum(1 for _ in settings.label_sections())
    connections = datasources.list_connections(settings)

    return render_template(
        'config_hub.html',
        default_target=settings.default_printer,
        printer_status=status,
        status_color=color,
        templates_count=len(templates_available),
        overrides_count=overrides_count,
        connections_count=len(connections),
        os_label='Windows (USB/driver)' if printer.IS_WINDOWS else 'CUPS (macOS/Linux)',
    )


@bp.route('/config/printers', methods=['GET', 'POST'])
def printers():
    """Default printer + per-template overrides."""
    settings = _settings()
    settings.reload()

    if request.method == 'POST':
        action = request.form.get('action', 'save_default')

        if action == 'save_default':
            target = _compose_target(request.form)
            templates_dir = (request.form.get('templates_dir') or '').strip()
            if target:
                settings.set_default_printer(target)
                logging.info(f"Default printer set to: {target}")
            if templates_dir:
                settings.set_templates_dir(templates_dir)
                logging.info(f"Templates dir set to: {templates_dir}")

        elif action == 'save_label':
            template_file = (request.form.get('zpl_template_path') or '').strip()
            target = _compose_target(request.form)
            if template_file and target:
                settings.update_label(template_file, target)
                logging.info(f"Per-label config upserted: {template_file} -> {target}")

        elif action == 'delete_label':
            template_file = (request.form.get('zpl_template_path') or '').strip()
            if template_file and settings.remove_label(template_file):
                logging.info(f"Per-label config removed: {template_file}")

        return redirect(url_for('config.printers'))

    system_printers = printer.list_system_printers('')
    status, color = printer.printer_status(settings.default_printer)
    default_backend, _ = printer.parse_target(settings.default_printer)
    default_fields = _decompose_target(settings.default_printer)

    templates_available = zpl.list_templates(settings.templates_dir)

    label_configs = []
    for section, cfg in settings.label_sections():
        tpl = cfg.get('zpl_template_path', '')
        tgt = cfg.get('printer_name', '')
        label_configs.append({
            'section': section,
            'template': tpl,
            'target': tgt,
            'backend': printer.parse_target(tgt)[0],
        })

    return render_template(
        'config_printers.html',
        default_target=settings.default_printer,
        default_fields=default_fields,
        default_backend_name=default_backend,
        templates_dir=str(settings.templates_dir),
        system_printers=system_printers,
        templates_available=templates_available,
        label_configs=label_configs,
        printer_status=status,
        status_color=color,
        is_windows=printer.IS_WINDOWS,
        os_label='Windows (USB/driver)' if printer.IS_WINDOWS else 'CUPS (macOS/Linux)',
    )


@bp.route('/config/templates')
def templates_list():
    """List of templates, with links to edit fields / ZPL."""
    settings = _settings()
    settings.reload()

    templates_available = zpl.list_templates(settings.templates_dir)
    fields_by_template = {
        t: [s.to_dict() for s in fields_mod.load_fields(settings.templates_dir / t)]
        for t in templates_available
    }
    sidecar_status = {
        t: fields_mod.sidecar_path(settings.templates_dir / t).is_file()
        for t in templates_available
    }

    return render_template(
        'config_templates.html',
        templates_available=templates_available,
        fields_by_template=fields_by_template,
        sidecar_status=sidecar_status,
    )


@bp.route('/config/connections')
def connections_page():
    """Database connections used by lookup fields."""
    settings = _settings()
    settings.reload()

    connections = [c.to_dict() for c in datasources.list_connections(settings)]
    from zebra.datasources.mssql import driver_status
    mssql_drivers = driver_status()

    return render_template(
        'config_connections.html',
        connections=connections,
        datasource_types=datasources.available_types(),
        mssql_drivers=mssql_drivers,
    )


@bp.route('/config/test', methods=['POST'])
def test_target_route():
    target = _compose_target(request.form) or request.form.get('target', '')
    ok, message = printer.test_target(target)
    backend, _ = printer.parse_target(target)
    return jsonify({
        'ok': ok,
        'message': message,
        'target': target,
        'backend': backend,
    })


@bp.route('/config/print-test', methods=['POST'])
def print_test_route():
    target = _compose_target(request.form) or request.form.get('target', '')
    try:
        printer.print_test_label(target)
    except printer.PrinterError as e:
        return jsonify({'ok': False, 'message': str(e), 'target': target}), 400
    return jsonify({
        'ok': True,
        'message': f'Test label sent to {target}',
        'target': target,
    })


@bp.route('/config/fields/<path:template_file>', methods=['GET', 'POST', 'DELETE'])
def fields_editor(template_file):
    """Read / write / reset the field sidecar for a single template."""
    settings = _settings()
    settings.reload()
    path = zpl.resolve_template(settings.templates_dir, template_file)
    if path is None:
        return jsonify({'error': 'Invalid template'}), 404

    if request.method == 'GET':
        specs = fields_mod.load_fields(path)
        return jsonify({
            'template_file': template_file,
            'fields': [s.to_dict() for s in specs],
            'has_sidecar': fields_mod.sidecar_path(path).is_file(),
        })

    if request.method == 'DELETE':
        removed = fields_mod.remove_sidecar(path)
        return jsonify({'ok': True, 'removed': removed})

    # POST: upsert
    try:
        payload = request.get_json(force=True, silent=False) or {}
    except Exception as e:
        return jsonify({'error': f'Invalid JSON: {e}'}), 400

    raw = payload.get('fields')
    if not isinstance(raw, list):
        return jsonify({'error': '"fields" must be a list'}), 400

    try:
        specs = [fields_mod.FieldSpec.from_dict(item) for item in raw]
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

    # Duplicate key check
    seen = set()
    for s in specs:
        if s.key in seen:
            return jsonify({'error': f'Duplicate key: {s.key}'}), 400
        seen.add(s.key)

    fields_mod.save_sidecar(path, specs)
    logging.info(f"Saved sidecar for {template_file} with {len(specs)} fields")

    # Kick a background cache sync for any lookup pair in the saved
    # sidecar so the print form has data ready by the time the user
    # gets there.
    cache_scheduler.maybe_sync_after_save(current_app._get_current_object(), specs)

    return jsonify({
        'ok': True,
        'fields': [s.to_dict() for s in specs],
    })


_CONNECTION_NAME_RE = re.compile(r'^[a-zA-Z][a-zA-Z0-9_]{0,30}$')

# Plain-string options that survive a save() round-trip. Anything not in
# this list is silently dropped — that way unrelated form fields don't
# pollute the connection record.
_MSSQL_OPTION_KEYS = (
    'server', 'database', 'port', 'auth', 'username',
    'driver', 'driver_lib', 'encrypt', 'trust_server_certificate', 'timeout',
)


def _connection_options_from_form(form) -> dict[str, str]:
    return {k: (form.get(k) or '').strip() for k in _MSSQL_OPTION_KEYS}


def _connection_from_form(form) -> tuple[str, ConnectionConfig, str | None]:
    name = (form.get('connection_name') or '').strip()
    type_ = (form.get('connection_type') or 'mssql').strip().lower()
    options = _connection_options_from_form(form)
    cfg = ConnectionConfig(name=name, type=type_, options=options)
    raw_pwd = form.get('password')
    return (name, cfg, raw_pwd)


@bp.route('/config/connections', methods=['POST'])
def save_connection():
    settings = _settings()
    settings.reload()
    name, cfg, raw_pwd = _connection_from_form(request.form)

    if not _CONNECTION_NAME_RE.match(name):
        return jsonify({
            'ok': False,
            'message': 'Invalid name. Use letters, digits and underscores '
                       '(must start with a letter).',
        }), 400

    # Empty password from the form means "don't change it" when editing.
    existing = settings.get_connection(name) is not None
    password = raw_pwd if (raw_pwd or not existing) else None

    datasources.upsert_connection(settings, cfg, password)
    logging.info(f'Saved connection {name} ({cfg.type})')
    return jsonify({'ok': True, 'message': f'Saved connection "{name}"'})


@bp.route('/config/connections/<name>/delete', methods=['POST'])
def delete_connection(name):
    settings = _settings()
    settings.reload()
    if not _CONNECTION_NAME_RE.match(name):
        return jsonify({'ok': False, 'message': 'Invalid name'}), 400
    removed = datasources.remove_connection(settings, name)
    return jsonify({'ok': removed, 'message': 'Deleted' if removed else 'Not found'})


@bp.route('/config/connections/test', methods=['POST'])
def test_connection():
    """Try connecting with values straight from the form (no save needed)."""
    settings = _settings()
    settings.reload()
    name, cfg, raw_pwd = _connection_from_form(request.form)

    # If the user left the password blank but is testing an existing entry,
    # use the stored password.
    password = raw_pwd or ''
    if not password and name and settings.get_connection(name):
        password = settings.get_connection_password(name)

    try:
        ds = datasources.build_datasource(cfg, password=password)
    except DataSourceError as e:
        return jsonify({'ok': False, 'message': str(e)})

    ok, msg = ds.test()
    return jsonify({'ok': ok, 'message': msg})


@bp.route('/api/connections/<name>/tables')
def list_connection_tables(name):
    settings = _settings()
    settings.reload()
    cfg = datasources.get_connection(settings, name)
    if cfg is None:
        return jsonify({'error': 'Unknown connection'}), 404
    password = settings.get_connection_password(name)
    try:
        ds = datasources.build_datasource(cfg, password=password)
        tables = ds.list_tables()
    except DataSourceError as e:
        return jsonify({'error': str(e)}), 502
    return jsonify({'tables': tables})


@bp.route('/api/connections/<name>/sync_table', methods=['POST'])
def sync_connection_table(name):
    """Pull every row of ``table`` into the local cache for offline lookups."""
    settings = _settings()
    settings.reload()
    table = (request.args.get('table') or request.form.get('table') or '').strip()
    if not table:
        return jsonify({'error': 'Missing table'}), 400
    cfg = datasources.get_connection(settings, name)
    if cfg is None:
        return jsonify({'error': 'Unknown connection'}), 404
    password = settings.get_connection_password(name)
    db_path = current_app.config['DB_PATH']
    try:
        ds = datasources.build_datasource(cfg, password=password)
        result = lookup_cache.sync_table(db_path, ds, table)
    except DataSourceError as e:
        return jsonify({'error': str(e)}), 502
    return jsonify({'ok': True, **result})


@bp.route('/api/cache/<name>/meta')
def cache_meta(name):
    """Return the current cache status for one (connection, table)."""
    table = (request.args.get('table') or '').strip()
    if not table:
        return jsonify({'error': 'Missing table'}), 400
    db_path = current_app.config['DB_PATH']
    meta = lookup_cache.get_meta(db_path, name, table)
    if meta is None:
        return jsonify({'connection': name, 'table': table,
                        'last_sync': None, 'row_count': 0, 'columns': []})
    return jsonify({'connection': name, 'table': table, **meta})


@bp.route('/api/cache/status')
def cache_status():
    """Return the auto-sync scheduler's current status."""
    return jsonify(cache_scheduler.get_status())


@bp.route('/api/cache/<name>/clear', methods=['POST'])
def cache_clear(name):
    table = (request.args.get('table') or request.form.get('table') or '').strip()
    if not table:
        return jsonify({'error': 'Missing table'}), 400
    db_path = current_app.config['DB_PATH']
    removed = lookup_cache.clear(db_path, name, table)
    return jsonify({'ok': True, 'removed': removed})


@bp.route('/api/connections/<name>/columns')
def list_connection_columns(name):
    settings = _settings()
    settings.reload()
    table = (request.args.get('table') or '').strip()
    if not table:
        return jsonify({'error': 'Missing table'}), 400
    cfg = datasources.get_connection(settings, name)
    if cfg is None:
        return jsonify({'error': 'Unknown connection'}), 404
    password = settings.get_connection_password(name)
    try:
        ds = datasources.build_datasource(cfg, password=password)
        cols = ds.list_columns(table)
    except DataSourceError as e:
        return jsonify({'error': str(e)}), 502
    return jsonify({'columns': cols})


@bp.route('/config/profiles')
def profiles_page():
    """List, create, switch and delete profiles."""
    base_dir = Path(current_app.config['BASE_DIR'])
    active = profiles.active_name(base_dir)
    items = []
    for name in profiles.list_profiles(base_dir):
        d = profiles.profile_dir(base_dir, name)
        size_bytes = sum(p.stat().st_size for p in d.rglob('*') if p.is_file())
        items.append({
            'name': name,
            'is_active': name == active,
            'size_kb': max(1, size_bytes // 1024),
            'templates': len(list((d / 'templates_zpl').glob('*.zpl'))) if (d / 'templates_zpl').is_dir() else 0,
        })
    return render_template(
        'config_profiles.html',
        profiles=items,
        active_profile=active,
    )


@bp.route('/config/profiles/create', methods=['POST'])
def profiles_create():
    base_dir = Path(current_app.config['BASE_DIR'])
    name = (request.form.get('name') or '').strip()
    try:
        profiles.create_profile(base_dir, name)
    except (ValueError, FileExistsError) as e:
        return jsonify({'ok': False, 'message': str(e)}), 400
    return jsonify({'ok': True, 'message': f'Profile "{name}" created'})


@bp.route('/config/profiles/switch', methods=['POST'])
def profiles_switch():
    base_dir = Path(current_app.config['BASE_DIR'])
    name = (request.form.get('name') or '').strip()
    try:
        profiles.set_active(base_dir, name)
    except ValueError as e:
        return jsonify({'ok': False, 'message': str(e)}), 400
    return jsonify({
        'ok': True,
        'message': (
            f'Active profile set to "{name}". '
            'Restart the app for the change to take effect.'
        ),
        'restart_required': True,
    })


@bp.route('/config/profiles/delete', methods=['POST'])
def profiles_delete():
    base_dir = Path(current_app.config['BASE_DIR'])
    name = (request.form.get('name') or '').strip()
    try:
        profiles.delete_profile(base_dir, name)
    except (ValueError, FileNotFoundError) as e:
        return jsonify({'ok': False, 'message': str(e)}), 400
    return jsonify({'ok': True, 'message': f'Profile "{name}" deleted'})


# ---------------------------------------------------------------------------
# Settings → Tools (one-shot ZPL utilities)
# ---------------------------------------------------------------------------

@bp.route('/config/tools')
def tools_page():
    """Render the Tools tab with all printer utilities grouped."""
    settings = _settings()
    settings.reload()
    return render_template(
        'config_tools.html',
        groups=printer_tools.GROUP_ORDER,
        tools_by_group=printer_tools.grouped(),
        default_target=settings.default_printer,
    )


@bp.route('/api/tools/run', methods=['POST'])
def tools_run():
    """Send a tool's ZPL to the chosen printer (or the default).

    Body: { "tool_id": "config_label", "target": "win://Foo" (optional) }
    """
    body = request.get_json(silent=True) or request.form.to_dict()
    tool = printer_tools.by_id((body.get('tool_id') or '').strip())
    if not tool:
        return jsonify({'ok': False, 'message': 'unknown tool'}), 400

    target = (body.get('target') or '').strip() or _settings().default_printer
    if not target:
        return jsonify({
            'ok': False,
            'message': 'No printer configured. Set one in Settings → Printers first.',
        }), 400

    try:
        printer.send_to_printer(target, tool['zpl'], copies=1)
    except printer.PrinterError as e:
        logging.warning(f'Tool {tool["id"]!r} failed on {target}: {e}')
        return jsonify({'ok': False, 'message': str(e)}), 500

    logging.info(f'Tool {tool["id"]!r} sent to {target}')
    return jsonify({'ok': True, 'message': f'Sent {tool["id"]} to {target}'})


@bp.route('/setup', methods=['GET', 'POST'])
def wizard():
    """Step-by-step first-run setup wizard."""
    settings = _settings()
    settings.reload()

    if request.method == 'POST':
        target = _compose_target(request.form)
        templates_dir = (request.form.get('templates_dir') or '').strip()
        if target:
            settings.set_default_printer(target)
            logging.info(f"Wizard saved default printer: {target}")
        if templates_dir:
            settings.set_templates_dir(templates_dir)
        return redirect(url_for('labels.index'))

    system_printers = printer.list_system_printers('')
    zebra_printers = printer.list_system_printers('zebra')
    default_fields = _decompose_target(settings.default_printer)

    return render_template(
        'wizard.html',
        default_target=settings.default_printer,
        default_fields=default_fields,
        templates_dir=str(settings.templates_dir),
        system_printers=system_printers,
        zebra_printers=zebra_printers,
        is_windows=printer.IS_WINDOWS,
        os_label='Windows (USB / driver)' if printer.IS_WINDOWS else 'macOS / Linux (CUPS)',
    )
