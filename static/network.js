/* Settings → Network: edit my identity, browse LAN peers, pull from one. */
(function () {
    'use strict';

    // ------------------------------------------------------------------
    // My identity (peer name, share toggles, PIN)
    // ------------------------------------------------------------------

    const $ = (id) => document.getElementById(id);

    function showResult(el, msg, isError) {
        if (!el) return;
        el.textContent = msg;
        el.className = 'test-result' + (isError ? ' error' : ' ok');
    }

    document.addEventListener('DOMContentLoaded', function () {
        const saveBtn = $('netSaveMe');
        if (saveBtn) saveBtn.addEventListener('click', async function () {
            const body = {
                peer_name:        $('netPeerName').value,
                share_templates:  $('netShareTemplates').checked,
                share_connections: $('netShareConnections').checked,
            };
            try {
                const r = await fetch('/api/network/me', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body),
                });
                if (!r.ok) throw new Error('HTTP ' + r.status);
                showResult($('netSaveResult'), 'OK', false);
            } catch (e) {
                showResult($('netSaveResult'), 'Error: ' + e, true);
            }
        });

        const regenBtn = $('netPinRegen');
        if (regenBtn) regenBtn.addEventListener('click', async function () {
            if (!confirm('Roll a new PIN? Existing peers will need to re-enter it.')) return;
            try {
                const r = await fetch('/api/network/pin/regenerate', { method: 'POST' });
                const j = await r.json();
                if (j.pin) $('netPin').textContent = j.pin;
            } catch (e) { /* swallow */ }
        });

        const refreshBtn = $('netRefreshPeers');
        if (refreshBtn) refreshBtn.addEventListener('click', refreshPeers);

        // Browse buttons on each peer card.
        document.querySelectorAll('#netPeersList [data-action="browse"]').forEach(wireBrowse);

        // Manual peer form (mDNS fallback)
        const addForm = document.getElementById('netAddPeerForm');
        if (addForm) addForm.addEventListener('submit', addManualPeer);

        // Auto-refresh peers every 5s — mDNS announcements arrive over time.
        setInterval(refreshPeers, 5000);

        // Diagnostics: load on page open, reload on user click + every 10s.
        const diagBtn = $('netDiagRefresh');
        if (diagBtn) diagBtn.addEventListener('click', refreshDiagnostics);
        refreshDiagnostics();
        setInterval(refreshDiagnostics, 10000);
    });

    async function refreshDiagnostics() {
        try {
            const r = await fetch('/api/network/diagnostics');
            const d = await r.json();
            paintDiagnostics(d);
        } catch (e) { /* swallow */ }
    }

    function paintDiagnostics(d) {
        const set = (key, val, isBoolGood) => {
            const el = document.querySelector(`#netDiagGrid [data-key="${key}"]`);
            if (!el) return;
            if (typeof val === 'boolean') {
                el.textContent = val ? '✓' : '✗';
                el.className = 'net-diag__val ' + (val === isBoolGood ? 'ok' : 'warn');
            } else {
                el.textContent = (val === null || val === undefined) ? '—' : String(val);
                el.className = 'net-diag__val';
            }
        };
        set('zeroconf_available', d.zeroconf_available, true);
        set('browser_active',     d.browser_active,     true);
        set('publisher_active',   d.publisher_active,   true);
        set('local_ip',           d.local_ip);
        set('peer_count',         d.peer_count);

        // Advice: render each code as a translated paragraph. We rely on
        // pre-rendered translations injected as data attributes by Jinja
        // (see below) so JS doesn't need its own catalog.
        const cont = document.getElementById('netDiagAdvice');
        cont.innerHTML = '';
        (d.advice || []).forEach(code => {
            const txt = window.NETWORK_ADVICE_I18N && window.NETWORK_ADVICE_I18N[code];
            if (!txt) return;
            const p = document.createElement('p');
            p.className = 'net-diag__tip';
            p.textContent = txt;
            cont.appendChild(p);
        });

        // Firewall section: show automatic button on Windows, manual
        // command snippet otherwise.
        const fwBox = document.getElementById('netFirewall');
        const fwManual = document.getElementById('netFwManual');
        const fwBtn = document.getElementById('netFwOpen');
        if (fwBox && d.firewall) {
            fwBox.hidden = false;
            const isWin = !!d.firewall.is_windows;
            if (fwBtn) fwBtn.hidden = !isWin;
            if (fwManual) {
                const cmd = (d.firewall.manual_instructions || {}).command || '';
                if (cmd) {
                    fwManual.textContent = cmd;
                    fwManual.hidden = false;
                } else {
                    fwManual.hidden = true;
                }
            }
        }
    }

    document.addEventListener('DOMContentLoaded', function () {
        const fwBtn = document.getElementById('netFwOpen');
        if (fwBtn) fwBtn.addEventListener('click', async function () {
            try {
                const r = await fetch('/api/network/firewall/open', { method: 'POST' });
                const j = await r.json();
                showResult(document.getElementById('netFwResult'), j.message || '', !j.ok);
            } catch (e) {
                showResult(document.getElementById('netFwResult'),
                           'Failed to open firewall helper: ' + e, true);
            }
        });
    });

    async function refreshPeers() {
        try {
            const r = await fetch('/api/network/peers');
            const data = await r.json();
            renderPeers(data.peers || []);
        } catch (e) { /* swallow */ }
    }

    function renderPeers(peers) {
        const list = $('netPeersList');
        if (!list) return;
        list.innerHTML = '';
        if (!peers.length) {
            const p = document.createElement('p');
            p.className = 'muted dashboard__empty';
            p.textContent = list.dataset.empty || '';
            list.appendChild(p);
            return;
        }
        peers.forEach((peer) => {
            const card = document.createElement('article');
            card.className = 'net-peer';
            card.dataset.peer = JSON.stringify(peer);
            card.innerHTML = `
                <div class="net-peer__main">
                    <div class="net-peer__name"></div>
                    <div class="net-peer__meta">
                        <code></code>
                        <span class="net-peer__profile" hidden></span>
                        <span class="net-peer__version" hidden></span>
                        <span class="net-peer__manual" hidden>· manual</span>
                    </div>
                </div>
                <div class="net-peer__actions">
                    <button type="button" class="btn-ghost" data-action="remove" hidden aria-label="Remove">×</button>
                    <button type="button" class="btn" data-action="browse">Browse →</button>
                </div>`;
            card.querySelector('.net-peer__name').textContent = peer.name || '(unnamed)';
            card.querySelector('code').textContent = `${peer.address}:${peer.port}`;
            if (peer.profile) {
                const sp = card.querySelector('.net-peer__profile');
                sp.textContent = '· ' + peer.profile;
                sp.hidden = false;
            }
            if (peer.version) {
                const sv = card.querySelector('.net-peer__version');
                sv.textContent = '· v' + peer.version;
                sv.hidden = false;
            }
            if (peer.manual) {
                card.querySelector('.net-peer__manual').hidden = false;
                const rm = card.querySelector('[data-action="remove"]');
                rm.hidden = false;
                rm.addEventListener('click', () => removeManualPeer(peer.address, peer.port));
            }
            wireBrowse(card.querySelector('[data-action="browse"]'));
            list.appendChild(card);
        });
    }

    async function addManualPeer(ev) {
        ev.preventDefault();
        const addr = document.getElementById('netAddPeerAddress').value.trim();
        const port = parseInt(document.getElementById('netAddPeerPort').value, 10) || 0;
        const out = document.getElementById('netAddPeerResult');
        if (!addr || !port) {
            showResult(out, 'Address + port required', true);
            return;
        }
        showResult(out, 'Probing…', false);
        try {
            const r = await fetch('/api/network/peers/manual', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ address: addr, port: port }),
            });
            const data = await r.json();
            if (!r.ok || !data.ok) {
                showResult(out, data.error || ('HTTP ' + r.status), true);
                return;
            }
            showResult(out, 'Added: ' + (data.peer.name || addr), false);
            document.getElementById('netAddPeerAddress').value = '';
            document.getElementById('netAddPeerPort').value = '';
            await refreshPeers();
        } catch (e) {
            showResult(out, 'Network error: ' + e, true);
        }
    }

    async function removeManualPeer(address, port) {
        try {
            await fetch('/api/network/peers/manual', {
                method: 'DELETE',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ address, port }),
            });
            await refreshPeers();
        } catch (e) { /* swallow */ }
    }

    // ------------------------------------------------------------------
    // Pull dialog
    // ------------------------------------------------------------------

    let currentPeer = null;

    function wireBrowse(btn) {
        if (!btn || btn._wired) return;
        btn._wired = true;
        btn.addEventListener('click', function () {
            const card = btn.closest('.net-peer');
            if (!card) return;
            try {
                currentPeer = JSON.parse(card.dataset.peer || '{}');
            } catch (e) { currentPeer = null; }
            if (!currentPeer || !currentPeer.url) return;
            openPullDialog();
        });
    }

    function openPullDialog() {
        const dlg = $('netPullDialog');
        if (!dlg) return;
        $('netPullTitle').textContent = (currentPeer && currentPeer.name) || '';
        $('netPullList').hidden = true;
        $('netPullPin').hidden = false;
        $('netPullPinInput').value = '';
        showResult($('netPullPinError'), '', false);
        showResult($('netPullResult'), '', false);
        if (typeof dlg.showModal === 'function') dlg.showModal();
        else dlg.setAttribute('open', '');
        $('netPullPinInput').focus();
    }

    function closePullDialog() {
        const dlg = $('netPullDialog');
        if (!dlg) return;
        if (typeof dlg.close === 'function') dlg.close();
        else dlg.removeAttribute('open');
    }

    document.addEventListener('DOMContentLoaded', function () {
        const dlg = $('netPullDialog');
        if (!dlg) return;
        $('netPullClose').addEventListener('click', closePullDialog);
        $('netPullCancel').addEventListener('click', closePullDialog);
        $('netPullPinSubmit').addEventListener('click', submitPin);
        $('netPullPinInput').addEventListener('keydown', (e) => {
            if (e.key === 'Enter') submitPin();
        });
        $('netPullImport').addEventListener('click', doImport);
    });

    async function submitPin() {
        if (!currentPeer || !currentPeer.url) return;
        const pin = ($('netPullPinInput').value || '').trim();
        if (!/^\d{6}$/.test(pin)) {
            showResult($('netPullPinError'), 'PIN must be 6 digits', true);
            return;
        }
        const peerB64 = btoa(currentPeer.url).replace(/=+$/, '')
            .replace(/\+/g, '-').replace(/\//g, '_');
        try {
            const r = await fetch('/api/network/peer/' + peerB64 + '/list', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ pin: pin }),
            });
            const data = await r.json();
            if (data.error === 'invalid_pin') {
                showResult($('netPullPinError'), 'Wrong PIN', true);
                return;
            }
            if (data.error) {
                showResult($('netPullPinError'), 'Could not reach peer: ' + data.error, true);
                return;
            }
            currentPeer._pin = pin;
            renderPullList(data.templates || [], data.connections || []);
            $('netPullPin').hidden = true;
            $('netPullList').hidden = false;
        } catch (e) {
            showResult($('netPullPinError'), 'Network error: ' + e, true);
        }
    }

    function renderPullList(templates, connections) {
        const tpl = $('netPullTemplates');
        const cn  = $('netPullConnections');
        tpl.innerHTML = '';
        cn.innerHTML  = '';

        if (!templates.length) {
            const li = document.createElement('li');
            li.className = 'muted';
            li.textContent = tpl.dataset.empty || '';
            tpl.appendChild(li);
        } else {
            templates.forEach((t) => {
                const li = document.createElement('li');
                li.innerHTML = `<label class="checkbox">
                    <input type="checkbox" name="tpl" value="" checked>
                    <code></code>
                </label>`;
                li.querySelector('input').value = t.file;
                li.querySelector('code').textContent = t.file;
                tpl.appendChild(li);
            });
        }

        if (!connections.length) {
            const li = document.createElement('li');
            li.className = 'muted';
            li.textContent = cn.dataset.empty || '';
            cn.appendChild(li);
        } else {
            connections.forEach((c) => {
                const li = document.createElement('li');
                li.innerHTML = `<label class="checkbox">
                    <input type="checkbox" name="conn" value="">
                    <code></code>
                    <span class="muted"></span>
                </label>`;
                li.querySelector('input').value = c.name;
                li.querySelector('code').textContent = c.name;
                li.querySelector('.muted').textContent = ' · ' + (c.type || '?');
                cn.appendChild(li);
            });
        }
    }

    async function doImport() {
        if (!currentPeer || !currentPeer._pin) return;
        const tplFiles = Array.from(document.querySelectorAll('#netPullTemplates input[name="tpl"]:checked'))
            .map((el) => el.value);
        const connNames = Array.from(document.querySelectorAll('#netPullConnections input[name="conn"]:checked'))
            .map((el) => el.value);
        if (!tplFiles.length && !connNames.length) {
            showResult($('netPullResult'), 'Nothing selected', true);
            return;
        }
        const summary = [];
        try {
            if (tplFiles.length) {
                const r = await fetch('/api/network/pull/templates', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        peer_url: currentPeer.url,
                        pin: currentPeer._pin,
                        files: tplFiles,
                    }),
                });
                const j = await r.json();
                summary.push(`Templates: ${(j.imported || []).length} imported, ${(j.errors || []).length} errors`);
            }
            if (connNames.length) {
                const r = await fetch('/api/network/pull/connections', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        peer_url: currentPeer.url,
                        pin: currentPeer._pin,
                        names: connNames,
                    }),
                });
                const j = await r.json();
                summary.push(`Connections: ${(j.imported || []).length} imported, ${(j.errors || []).length} errors`);
            }
            showResult($('netPullResult'), summary.join(' · '), false);
        } catch (e) {
            showResult($('netPullResult'), 'Import failed: ' + e, true);
        }
    }
})();
