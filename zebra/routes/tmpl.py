"""Template authoring routes.

The editor doesn't try to replace ZebraDesigner — it accepts the ZPL that
another tool produced and lets the user pick which static strings should
become variables at print time.

Endpoints
---------

* ``GET  /templates/new``                Blank editor (skeleton / paste / upload).
* ``POST /templates/new``                Parse submitted ZPL → mapping page.
* ``GET  /templates/<name>/edit``        Re-open an existing template.
* ``POST /templates/save``               Persist .zpl + sidecar JSON.
* ``POST /templates/<name>/delete``      Remove .zpl, sidecar and any printer
                                         override for the template.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from flask import (
    Blueprint, current_app, flash, jsonify, redirect, render_template, request,
    url_for,
)

from zebra import datasources, fields as fields_mod
from zebra import zpl as zpl_mod
from zebra import zpl_parser

bp = Blueprint('tmpl', __name__)

_NAME_RE = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_\- ]{0,60}$')


def _settings():
    return current_app.config['SETTINGS']


def _templates_dir() -> Path:
    return _settings().templates_dir


def _template_path(name: str) -> Path | None:
    """Return a safe path inside the templates dir, or None if invalid."""
    clean = (name or '').strip()
    if not clean.endswith('.zpl'):
        clean = clean + '.zpl'
    base = clean[:-4]
    if not _NAME_RE.match(base):
        return None
    return _templates_dir() / clean


def _skeleton(width_dots: int = 800, length_dots: int = 1200,
              darkness: int = 15, speed: int = 4) -> str:
    """Generate a minimal valid ZPL skeleton."""
    return (
        "^XA\n"
        f"^PW{width_dots}\n"
        f"^LL{length_dots}\n"
        f"^MD{darkness}\n"
        f"^PR{speed}\n"
        "^CI28\n"
        "^CF0,40\n"
        "^FO40,40^FDNew Label^FS\n"
        "^XZ\n"
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@bp.route('/templates/new', methods=['GET', 'POST'])
def new():
    if request.method == 'GET':
        return render_template(
            'template_new.html',
            skeleton=_skeleton(),
            existing_names=sorted(zpl_mod.list_templates(_templates_dir())),
        )

    # POST: first pass — parse the uploaded/pasted ZPL → show mapping
    source = (request.form.get('source') or 'paste').strip()
    if source == 'upload':
        file = request.files.get('file')
        if not file:
            flash('No file uploaded', 'error')
            return redirect(url_for('tmpl.new'))
        zpl_text = file.read().decode('utf-8', errors='replace')
        name = request.form.get('template_name') or Path(file.filename or 'new').stem
    elif source == 'skeleton':
        zpl_text = _skeleton(
            width_dots=_int(request.form.get('width'), 800, 1, 4000),
            length_dots=_int(request.form.get('length'), 1200, 1, 6000),
            darkness=_int(request.form.get('darkness'), 15, 0, 30),
            speed=_int(request.form.get('speed'), 4, 1, 14),
        )
        name = request.form.get('template_name') or 'new_label'
    else:
        zpl_text = request.form.get('zpl', '')
        name = request.form.get('template_name') or 'new_label'

    blocks = zpl_parser.parse_fd_blocks(zpl_text)
    existing_keys = _existing_keys(name)

    return render_template(
        'template_map.html',
        name=(name or '').strip(),
        edit_mode=bool(request.form.get('edit_mode')),
        zpl_text=zpl_text,
        blocks=blocks,
        already_parameterised=zpl_parser.already_parameterised,
        existing_keys=existing_keys,
    )


@bp.route('/templates/<path:name>/fields')
def fields(name):
    """Dedicated page for editing a template's field definitions."""
    settings = _settings()
    settings.reload()

    path = _template_path(name)
    if path is None or not path.is_file():
        return redirect(url_for('config.config_page'))

    specs = fields_mod.load_fields(path)
    has_sidecar = fields_mod.sidecar_path(path).is_file()
    connections = [c.to_dict() for c in datasources.list_connections(settings)]
    print_settings = fields_mod.load_print_settings(path)

    return render_template(
        'template_fields.html',
        template_name=path.stem,
        template_file=path.name,
        fields=[s.to_dict() for s in specs],
        has_sidecar=has_sidecar,
        connections=connections,
        print_settings=print_settings,
    )


@bp.route('/api/templates/<path:name>/versions')
def template_versions(name):
    """List saved versions for a template, newest first."""
    path = _template_path(name)
    if path is None or not path.is_file():
        return jsonify({'error': 'Invalid template'}), 404
    from zebra import template_history
    return jsonify({'versions': template_history.list_versions(path)})


@bp.route('/api/templates/<path:name>/versions/<ts>')
def template_version_get(name, ts):
    """Return the contents of one version (for preview)."""
    path = _template_path(name)
    if path is None:
        return jsonify({'error': 'Invalid template'}), 404
    from zebra import template_history
    data = template_history.get_version(path, ts)
    if data is None:
        return jsonify({'error': 'Unknown version'}), 404
    return jsonify(data)


@bp.route('/api/templates/<path:name>/versions/<ts>/restore', methods=['POST'])
def template_version_restore(name, ts):
    """Restore a saved version. The current file is snapshotted first."""
    path = _template_path(name)
    if path is None or not path.is_file():
        return jsonify({'error': 'Invalid template'}), 404
    from zebra import template_history
    if not template_history.restore_version(path, ts):
        return jsonify({'ok': False, 'error': 'Could not restore'}), 400
    return jsonify({'ok': True, 'restored': ts})


@bp.route('/templates/<path:name>/print_settings', methods=['POST'])
def save_template_print_settings(name):
    """Persist per-template printer overrides (media type, speed, darkness)."""
    path = _template_path(name)
    if path is None or not path.is_file():
        return redirect(url_for('config.config_page'))
    fields_mod.save_print_settings(path, {
        'media_type': request.form.get('media_type', ''),
        'speed_ips':  request.form.get('speed_ips', 0),
        'darkness':   request.form.get('darkness', -1),
    })
    return redirect(url_for('tmpl.fields', name=name))


@bp.route('/templates/<path:name>/source', methods=['GET', 'POST'])
def source(name):
    """Free-form ZPL editor with live preview.

    GET returns the current file content; POST overwrites it. Only the ZPL
    is touched here — the sidecar (fields) is left untouched. Use
    ``/templates/<name>/edit`` to re-identify variables after structural
    edits if you added new ``^FD…^FS`` blocks.
    """
    path = _template_path(name)
    if path is None or not path.is_file():
        if request.method == 'POST':
            return jsonify({'ok': False, 'error': 'Template not found'}), 404
        return redirect(url_for('config.templates_list'))

    if request.method == 'POST':
        zpl_text = request.form.get('zpl', '')
        if not zpl_text.strip():
            return jsonify({'ok': False, 'error': 'ZPL cannot be empty'}), 400
        # Snapshot the current file before overwriting so the user can
        # restore from Settings → Templates → Edit → Versions.
        from zebra import template_history
        template_history.snapshot(path, reason='zpl_edit')
        path.write_text(zpl_text, encoding='utf-8')
        logging.info(f"Saved ZPL source for {path.name}")
        return jsonify({'ok': True, 'bytes': len(zpl_text)})

    zpl_text = path.read_text(encoding='utf-8', errors='replace')
    return render_template(
        'template_source.html',
        template_name=path.stem,
        template_file=path.name,
        zpl_text=zpl_text,
    )


@bp.route('/templates/<path:name>/edit')
def edit(name):
    """Open an existing template in the mapping editor."""
    path = _template_path(name)
    if path is None or not path.is_file():
        return redirect(url_for('config.config_page'))

    zpl_text = path.read_text(encoding='utf-8', errors='replace')
    blocks = zpl_parser.parse_fd_blocks(zpl_text)
    return render_template(
        'template_map.html',
        name=path.stem,
        edit_mode=True,
        zpl_text=zpl_text,
        blocks=blocks,
        already_parameterised=zpl_parser.already_parameterised,
        existing_keys=_existing_keys(path.stem),
    )


@bp.route('/templates/save', methods=['POST'])
def save():
    name = (request.form.get('template_name') or '').strip()
    zpl_text = request.form.get('zpl', '')
    edit_mode = bool(request.form.get('edit_mode'))

    path = _template_path(name)
    if path is None:
        return _map_error('Invalid template name.', name, zpl_text)

    if not edit_mode and path.is_file():
        return _map_error(
            f'"{path.name}" already exists — use Edit instead.',
            name, zpl_text,
        )

    blocks = zpl_parser.parse_fd_blocks(zpl_text)

    # Collect user's mapping choices from the form
    selected: dict[int, str] = {}
    for block in blocks:
        if not request.form.get(f'map_{block.index}'):
            continue
        key = (request.form.get(f'key_{block.index}') or '').strip()
        if not key:
            continue
        if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]{0,39}$', key):
            return _map_error(f'Invalid field key: {key!r}', name, zpl_text)
        if key in selected.values():
            return _map_error(f'Duplicate field key: {key}', name, zpl_text)
        selected[block.index] = key

    # Write the parameterised template
    path.parent.mkdir(parents=True, exist_ok=True)
    rewritten = zpl_parser.rewrite_with_placeholders(zpl_text, selected)
    path.write_text(rewritten, encoding='utf-8')

    # Build + save sidecar (only when we actually created variables)
    if selected:
        raw_fields = zpl_parser.blocks_to_sidecar_fields(blocks, selected)
        specs = [fields_mod.FieldSpec.from_dict(f) for f in raw_fields]
        fields_mod.save_sidecar(path, specs)
    else:
        # No variables — remove any stale sidecar
        fields_mod.remove_sidecar(path)

    logging.info(f"Saved template {path.name} with {len(selected)} variables")
    flash(f'Saved {path.name}', 'success')
    return redirect(url_for('labels.index'))


@bp.route('/templates/<path:name>/delete', methods=['POST'])
def delete(name):
    path = _template_path(name)
    if path is None or not path.is_file():
        return redirect(url_for('config.config_page'))

    # Remove ZPL + sidecar + any label_* override in config.cfg
    sidecar = fields_mod.sidecar_path(path)
    if sidecar.is_file():
        sidecar.unlink()
    path.unlink()
    _settings().remove_label(path.name)

    logging.info(f"Deleted template {path.name}")
    flash(f'Deleted {path.name}', 'success')
    return redirect(url_for('config.config_page'))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _int(raw, default: int, lo: int, hi: int) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, value))


def _existing_keys(template_name: str) -> list[str]:
    """Known field keys from the sidecar, for suggesting reuse."""
    base = (template_name or '').strip()
    if not base.endswith('.zpl'):
        base = base + '.zpl'
    path = _templates_dir() / base
    if not path.is_file():
        return []
    specs = fields_mod.load_fields(path)
    return [s.key for s in specs]


def _map_error(message: str, name: str, zpl_text: str):
    flash(message, 'error')
    blocks = zpl_parser.parse_fd_blocks(zpl_text)
    return render_template(
        'template_map.html',
        name=name,
        edit_mode=True,
        zpl_text=zpl_text,
        blocks=blocks,
        already_parameterised=zpl_parser.already_parameterised,
        existing_keys=_existing_keys(name),
    )
