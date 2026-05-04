"""HTTP routes for LAN peer discovery and template/connection sharing.

Two surfaces live here:

  /api/network/*   — used by *this* instance's UI (Settings → Network).
  /api/peer/*      — used by *other* instances pulling from us.
                     Authenticated with the share PIN.

The PIN check is intentionally simple: ``?pin=NNNNNN`` query param vs
the value in :mod:`zebra.network`. We're on the LAN over plain HTTP, so
sophisticated auth would be theatre. The point of the PIN is to stop a
random colleague on the same wifi from silently scraping your templates.
"""

from __future__ import annotations

import logging
from pathlib import Path

from flask import (
    Blueprint, current_app, jsonify, render_template, request, url_for,
)

from zebra import datasources, discovery, fields as fields_mod, firewall, network
from zebra.routes.config import _settings


bp = Blueprint('network', __name__)


# ---------------------------------------------------------------------------
# Local-UI endpoints (no auth — same machine)
# ---------------------------------------------------------------------------

@bp.route('/api/network/me')
def me():
    """Return this instance's identity + share prefs (PIN included)."""
    snap = network.snapshot()
    snap['address'] = discovery.local_ip()
    snap['port'] = int(current_app.config.get('DISCOVERY_PORT') or 0)
    snap['profile'] = current_app.config.get('PROFILE_NAME', '')
    return jsonify(snap)


@bp.route('/api/network/me', methods=['POST'])
def update_me():
    """Update peer name / share toggles. Restarts mDNS publisher if the
    name changed so peers see the new label immediately."""
    body = request.get_json(silent=True) or request.form.to_dict()
    old_name = network.peer_name()
    snap = network.update({
        k: body[k] for k in ('peer_name', 'share_templates', 'share_connections')
        if k in body
    })
    if snap.get('peer_name') != old_name:
        from zebra import __version__
        port = int(current_app.config.get('DISCOVERY_PORT') or 0)
        discovery.get_discovery().start(
            peer_name=snap['peer_name'],
            version=__version__,
            profile=current_app.config.get('PROFILE_NAME', ''),
            port=port,
        )
    snap['address'] = discovery.local_ip()
    snap['port'] = int(current_app.config.get('DISCOVERY_PORT') or 0)
    return jsonify(snap)


@bp.route('/api/network/pin/regenerate', methods=['POST'])
def regen_pin():
    """Roll a new 6-digit PIN. Existing peers will have to re-enter it."""
    return jsonify({'pin': network.regenerate_pin()})


@bp.route('/api/network/peers')
def peers():
    """Peers currently visible: mDNS-discovered + manually-added by IP.

    Manual entries get ``manual: true`` so the UI can label them and
    offer a Remove button.
    """
    discovered = [p.to_dict() for p in discovery.get_peers()]
    for p in discovered:
        p['manual'] = False

    # Avoid duplicates: if a manual peer happens to also be discovered
    # via mDNS, keep the discovered one (richer metadata) and drop the
    # manual entry from the list (but not from storage — user might
    # want it later if mDNS dies).
    discovered_keys = {(p['address'], p['port']) for p in discovered}
    manuals = [
        {**m,
         'url': f"http://{m['address']}:{m['port']}",
         'version': '',
         'profile': ''}
        for m in network.manual_peers()
        if (m['address'], m['port']) not in discovered_keys
    ]
    return jsonify({'peers': discovered + manuals})


@bp.route('/api/network/peers/manual', methods=['POST'])
def add_manual_peer():
    """Probe an address/port pair, add it to the manual list if alive."""
    import requests as _r
    body = request.get_json(silent=True) or request.form.to_dict()
    address = (body.get('address') or '').strip()
    try:
        port = int(body.get('port') or 0)
    except (TypeError, ValueError):
        port = 0
    if not address or port <= 0:
        return jsonify({'ok': False, 'error': 'address and port required'}), 400

    # Probe /api/peer/info — fast sanity check that something
    # comandante-zebra-shaped is listening there.
    name = ''
    try:
        r = _r.get(f'http://{address}:{port}/api/peer/info', timeout=3)
        if r.status_code == 200:
            data = r.json()
            name = (data or {}).get('peer_name', '') or ''
        else:
            return jsonify({
                'ok': False,
                'error': f'HTTP {r.status_code} from {address}:{port}',
            }), 400
    except Exception as e:  # noqa: BLE001
        return jsonify({
            'ok': False,
            'error': f'Could not reach {address}:{port}: {e}',
        }), 400

    saved = network.add_manual_peer(address, port, name)
    return jsonify({'ok': True, 'peer': saved})


@bp.route('/api/network/peers/manual', methods=['DELETE'])
def remove_manual_peer():
    """Body or query: { address, port }."""
    body = request.get_json(silent=True) or request.args.to_dict()
    address = (body.get('address') or '').strip()
    try:
        port = int(body.get('port') or 0)
    except (TypeError, ValueError):
        port = 0
    removed = network.remove_manual_peer(address, port)
    return jsonify({'ok': removed})


@bp.route('/api/network/diagnostics')
def diagnostics():
    """Status snapshot used by the Network page to surface mDNS issues."""
    diag = discovery.get_discovery().diagnostics()
    diag['firewall'] = {
        **firewall.os_info(),
        'manual_instructions': firewall.manual_instructions(),
    }
    return jsonify(diag)


@bp.route('/api/network/firewall/open', methods=['POST'])
def open_firewall():
    """Trigger an elevated PowerShell to add the mDNS firewall rule.

    Windows-only. On other OSes returns 400 with manual instructions.
    """
    if not firewall.is_windows():
        return jsonify({
            'ok': False,
            'message': 'Automatic firewall opening is Windows-only.',
            'manual': firewall.manual_instructions(),
        }), 400
    launched, msg = firewall.open_mdns_windows()
    return jsonify({'ok': launched, 'message': msg})


# ---------------------------------------------------------------------------
# Peer-facing endpoints (PIN-authenticated, called by other instances)
# ---------------------------------------------------------------------------

@bp.route('/api/peer/info')
def peer_info():
    """Public info — no PIN required.

    Lets a calling client see what this peer is willing to share before
    asking for the PIN. We don't expose the PIN here; the client supplies
    it on follow-up requests.
    """
    snap = network.snapshot()
    return jsonify({
        'peer_name':         snap.get('peer_name', ''),
        'profile':           current_app.config.get('PROFILE_NAME', ''),
        'share_templates':   snap.get('share_templates', True),
        'share_connections': snap.get('share_connections', False),
    })


def _check_pin_or_403():
    if not network.check_pin(request.args.get('pin') or request.headers.get('X-Peer-Pin')):
        return jsonify({'error': 'invalid PIN'}), 403
    return None


@bp.route('/api/peer/templates')
def peer_list_templates():
    """List shareable templates. Requires PIN. Empty if sharing is off."""
    err = _check_pin_or_403()
    if err is not None: return err
    if not network.shares_templates():
        return jsonify({'templates': []})
    s = _settings()
    s.reload()
    out: list[dict] = []
    for fname in sorted(_template_files()):
        path = s.templates_dir / fname
        sidecar = fields_mod.sidecar_path(path)
        out.append({
            'file':         fname,
            'has_sidecar':  sidecar.is_file(),
            'size_bytes':   path.stat().st_size if path.is_file() else 0,
        })
    return jsonify({'templates': out})


@bp.route('/api/peer/templates/<path:name>')
def peer_get_template(name):
    """Return the .zpl content + sidecar JSON for one template."""
    err = _check_pin_or_403()
    if err is not None: return err
    if not network.shares_templates():
        return jsonify({'error': 'templates not shared'}), 403
    # Reject anything that isn't a flat filename in our own list. The
    # whitelist check below is the real defence; the early sanity check
    # avoids touching the filesystem for obvious garbage.
    if '/' in name or '\\' in name or '..' in name:
        return jsonify({'error': 'invalid name'}), 400
    if name not in _template_files():
        return jsonify({'error': 'unknown template'}), 404
    s = _settings()
    s.reload()
    path = s.templates_dir / name
    payload = {
        'file': name,
        'zpl':  path.read_text(encoding='utf-8'),
    }
    sc = fields_mod.sidecar_path(path)
    if sc.is_file():
        try:
            payload['sidecar'] = sc.read_text(encoding='utf-8')
        except OSError:
            pass
    return jsonify(payload)


@bp.route('/api/peer/connections')
def peer_list_connections():
    """List shareable connections (sans secrets). Requires PIN."""
    err = _check_pin_or_403()
    if err is not None: return err
    if not network.shares_connections():
        return jsonify({'connections': []})
    s = _settings()
    s.reload()
    return jsonify({
        'connections': [
            _scrub(c.to_dict()) for c in datasources.list_connections(s)
        ]
    })


@bp.route('/api/peer/connections/<path:name>')
def peer_get_connection(name):
    err = _check_pin_or_403()
    if err is not None: return err
    if not network.shares_connections():
        return jsonify({'error': 'connections not shared'}), 403
    s = _settings()
    s.reload()
    for c in datasources.list_connections(s):
        if c.name == name:
            return jsonify(_scrub(c.to_dict()))
    return jsonify({'error': 'unknown connection'}), 404


# ---------------------------------------------------------------------------
# Pull endpoints — called by *our* UI to import from a peer
# ---------------------------------------------------------------------------

@bp.route('/api/network/pull/templates', methods=['POST'])
def pull_templates():
    """Download selected templates from a peer and write them locally.

    Body: { peer_url, pin, files: [...] }
    """
    import requests as _r
    body = request.get_json(silent=True) or {}
    peer_url = (body.get('peer_url') or '').rstrip('/')
    pin = body.get('pin') or ''
    files = body.get('files') or []
    if not peer_url or not pin or not isinstance(files, list):
        return jsonify({'error': 'peer_url, pin and files[] required'}), 400

    s = _settings()
    s.reload()
    target_dir: Path = s.templates_dir
    target_dir.mkdir(parents=True, exist_ok=True)

    imported, errors = [], []
    for fname in files:
        # Defensive: only accept plain .zpl filenames. Stops a malicious
        # peer from pushing "../../etc/passwd" or weird paths into us.
        if not isinstance(fname, str) or '/' in fname or '\\' in fname or '..' in fname:
            errors.append({'file': str(fname), 'error': 'invalid filename'})
            continue
        if not fname.lower().endswith('.zpl'):
            errors.append({'file': fname, 'error': 'not a .zpl file'})
            continue
        try:
            r = _r.get(
                f'{peer_url}/api/peer/templates/{fname}',
                params={'pin': pin}, timeout=8,
            )
            if r.status_code != 200:
                errors.append({'file': fname, 'status': r.status_code})
                continue
            data = r.json()
            zpl_text = data.get('zpl', '')
            if not isinstance(zpl_text, str):
                errors.append({'file': fname, 'error': 'malformed payload'})
                continue
            (target_dir / fname).write_text(zpl_text, encoding='utf-8')
            sc = data.get('sidecar')
            if isinstance(sc, str):
                (target_dir / (fname + '.json')).write_text(sc, encoding='utf-8')
            imported.append(fname)
        except _r.RequestException as e:
            errors.append({'file': fname, 'error': f'network: {e}'})
        except OSError as e:
            errors.append({'file': fname, 'error': f'disk: {e}'})
        except Exception as e:  # noqa: BLE001
            errors.append({'file': fname, 'error': str(e)})

    return jsonify({'imported': imported, 'errors': errors})


@bp.route('/api/network/pull/connections', methods=['POST'])
def pull_connections():
    """Download selected connection definitions from a peer (no passwords).

    Body: { peer_url, pin, names: [...] }
    """
    import requests as _r
    body = request.get_json(silent=True) or {}
    peer_url = (body.get('peer_url') or '').rstrip('/')
    pin = body.get('pin') or ''
    names = body.get('names') or []
    if not peer_url or not pin or not isinstance(names, list):
        return jsonify({'error': 'peer_url, pin and names[] required'}), 400

    s = _settings()
    s.reload()
    imported, errors = [], []
    for n in names:
        try:
            r = _r.get(
                f'{peer_url}/api/peer/connections/{n}',
                params={'pin': pin}, timeout=8,
            )
            if r.status_code != 200:
                errors.append({'name': n, 'status': r.status_code})
                continue
            data = r.json()
            cfg = datasources.ConnectionConfig(
                name=str(data.get('name', n)),
                type=str(data.get('type', '')),
                options=dict(data.get('options') or {}),
            )
            # password=None: receiver supplies their own credentials in
            # Settings → Connections after import. We never ship secrets
            # over the wire (and _scrub on the sender side enforces it).
            datasources.upsert_connection(s, cfg, password=None)
            imported.append(n)
        except Exception as e:  # noqa: BLE001
            errors.append({'name': n, 'error': str(e)})
    return jsonify({'imported': imported, 'errors': errors})


@bp.route('/api/network/peer/<path:peer_url_b64>/list', methods=['POST'])
def peer_remote_list(peer_url_b64):
    """Proxy: ask a peer for its templates+connections lists with a PIN."""
    import base64, requests as _r
    try:
        peer_url = base64.urlsafe_b64decode(peer_url_b64.encode()).decode().rstrip('/')
    except Exception:  # noqa: BLE001
        return jsonify({'error': 'bad peer_url'}), 400
    body = request.get_json(silent=True) or {}
    pin = body.get('pin') or ''
    out: dict = {'templates': [], 'connections': [], 'error': None}
    try:
        info = _r.get(f'{peer_url}/api/peer/info', timeout=5).json()
        out['info'] = info
        if info.get('share_templates'):
            r = _r.get(f'{peer_url}/api/peer/templates', params={'pin': pin}, timeout=5)
            if r.status_code == 200:
                out['templates'] = r.json().get('templates', [])
            elif r.status_code == 403:
                out['error'] = 'invalid_pin'
        if info.get('share_connections'):
            r = _r.get(f'{peer_url}/api/peer/connections', params={'pin': pin}, timeout=5)
            if r.status_code == 200:
                out['connections'] = r.json().get('connections', [])
    except Exception as e:  # noqa: BLE001
        out['error'] = str(e)
    return jsonify(out)


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

@bp.route('/config/network')
def network_page():
    snap = network.snapshot()
    snap['address'] = discovery.local_ip()
    snap['port'] = int(current_app.config.get('DISCOVERY_PORT') or 0)
    return render_template(
        'config_network.html',
        me=snap,
        peers=[p.to_dict() for p in discovery.get_peers()],
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _template_files() -> list[str]:
    """Return current .zpl filenames in the active profile."""
    s = _settings()
    s.reload()
    d = s.templates_dir
    if not d.is_dir():
        return []
    return [p.name for p in d.iterdir() if p.suffix == '.zpl']


def _scrub(conn: dict) -> dict:
    """Drop fields that look like secrets before sending a connection over."""
    out = dict(conn)
    opts = dict(out.get('options') or {})
    for k in list(opts.keys()):
        if k.lower() in ('password', 'pwd', 'secret', 'token', 'api_key'):
            opts.pop(k, None)
    out['options'] = opts
    return out
