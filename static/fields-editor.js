(function () {
    'use strict';

    const $ = (id) => document.getElementById(id);
    const editor = () => $('fieldsEditor');
    const listText = () => $('fieldsListText');
    const listDb = () => $('fieldsListDb');
    const summary = () => $('fieldsSummary');
    const sourceSel = () => $('dbSectionSource');
    const tableSel = () => $('dbSectionTable');
    const sectionStatus = () => $('dbSectionStatus');

    function showToast(msg, isError) {
        const t = document.getElementById('toast');
        if (!t) return;
        t.textContent = msg;
        t.classList.toggle('error', !!isError);
        t.style.display = 'block';
        clearTimeout(showToast._timer);
        showToast._timer = setTimeout(() => { t.style.display = 'none'; }, 3500);
    }

    async function withBusy(btn, fn) {
        if (!btn) return await fn();
        const wasDisabled = btn.disabled;
        btn.disabled = true;
        btn.classList.add('is-busy');
        try {
            return await fn();
        } finally {
            btn.disabled = wasDisabled;
            btn.classList.remove('is-busy');
        }
    }

    // Track unsaved changes to warn the user before navigating away.
    let _dirty = false;
    function markDirty() { _dirty = true; }
    function markClean() { _dirty = false; }
    window.addEventListener('beforeunload', (e) => {
        if (!_dirty) return;
        e.preventDefault();
        e.returnValue = '';
    });

    function templateFile() { return editor().dataset.templateFile; }
    function dataConnections() {
        try { return JSON.parse(editor().dataset.connections || '[]'); }
        catch (e) { return []; }
    }

    // ------------------------------------------------------------------
    // Section state — single connection + table for all lookups
    // ------------------------------------------------------------------

    const _section = { source: '', table: '', columns: [], cache: null };
    const tablesCache = new Map();   // connection -> [{name, kind}]
    const columnsCache = new Map();  // "conn::table" -> [columns]

    function setSectionStatus(msg, kind) {
        const el = sectionStatus();
        el.textContent = msg || '';
        el.classList.toggle('ok', kind === 'ok');
        el.classList.toggle('err', kind === 'err');
    }

    function initSectionControls() {
        const conns = dataConnections();
        const ss = sourceSel();
        ss.innerHTML = '';
        if (!conns.length) {
            ss.appendChild(new Option('-- create a connection first --', ''));
        } else {
            ss.appendChild(new Option('-- pick a connection --', ''));
            conns.forEach((c) => ss.appendChild(new Option(c.name + ' (' + c.type + ')', c.name)));
        }
        ss.value = _section.source || '';

        const ts = tableSel();
        ts.innerHTML = '<option value="">--</option>';
        if (_section.table) ts.appendChild(new Option(_section.table, _section.table, true, true));

        ss.addEventListener('change', async () => {
            _section.source = ss.value;
            _section.table = '';
            _section.columns = [];
            tableSel().innerHTML = '<option value="">--</option>';
            await refreshSectionTables();
            renderAllConfigTables();
            updateCacheBar();
        });
        ts.addEventListener('change', async () => {
            _section.table = ts.value;
            await refreshSectionColumns();
            renderAllConfigTables();
            await refreshCacheMeta();
            updateCacheBar();
        });
        $('dbReloadTables').addEventListener('click', async () => {
            tablesCache.delete(_section.source);
            await refreshSectionTables();
        });
        $('cacheSync').addEventListener('click', () => syncCache());
    }

    // ------------------------------------------------------------------
    // Offline cache (per connection + table)
    // ------------------------------------------------------------------

    async function refreshCacheMeta() {
        if (!_section.source || !_section.table) {
            _section.cache = null;
            return;
        }
        try {
            const res = await fetch('/api/cache/' + encodeURIComponent(_section.source) +
                '/meta?table=' + encodeURIComponent(_section.table));
            const data = await res.json().catch(() => ({}));
            if (!res.ok) {
                _section.cache = null;
                return;
            }
            _section.cache = {
                last_sync: data.last_sync || null,
                row_count: data.row_count || 0,
            };
        } catch (e) {
            _section.cache = null;
        }
    }

    function formatRelativeTime(isoStr) {
        if (!isoStr) return 'never';
        const d = new Date(isoStr);
        if (isNaN(d)) return isoStr;
        const diffMs = Date.now() - d.getTime();
        const diffSec = Math.round(diffMs / 1000);
        if (diffSec < 60) return 'just now';
        const diffMin = Math.round(diffSec / 60);
        if (diffMin < 60) return `${diffMin}m ago`;
        const diffH = Math.round(diffMin / 60);
        if (diffH < 24) return `${diffH}h ago`;
        const diffD = Math.round(diffH / 24);
        if (diffD < 30) return `${diffD}d ago`;
        return d.toLocaleDateString();
    }

    function updateCacheBar() {
        const bar = $('cacheBar');
        const status = $('cacheStatus');
        const btn = $('cacheSync');
        if (!_section.source || !_section.table) {
            bar.hidden = true;
            return;
        }
        bar.hidden = false;
        const c = _section.cache;
        if (!c || !c.last_sync) {
            status.innerHTML = '<strong class="cache-bar__warn">No data cached yet</strong> — lookups won\'t return any results until you sync.';
            btn.classList.add('btn');
            btn.classList.remove('btn-secondary');
        } else {
            const rel = formatRelativeTime(c.last_sync);
            const abs = new Date(c.last_sync).toLocaleString();
            status.innerHTML = `<strong>${c.row_count.toLocaleString()} rows cached</strong> · last sync <time title="${abs}">${rel}</time>`;
            btn.classList.add('btn-secondary');
            btn.classList.remove('btn');
        }
    }

    async function syncCache() {
        if (!_section.source || !_section.table) {
            showToast('Pick a connection and table first', true);
            return;
        }
        const status = $('cacheStatus');
        status.textContent = 'Syncing… this may take a moment on large views.';
        await withBusy($('cacheSync'), async () => {
            try {
                const res = await fetch('/api/connections/' + encodeURIComponent(_section.source) +
                    '/sync_table?table=' + encodeURIComponent(_section.table), { method: 'POST' });
                const data = await res.json().catch(() => ({}));
                if (!res.ok || !data.ok) {
                    showToast(data.error || 'Sync failed', true);
                    return;
                }
                _section.cache = { last_sync: data.last_sync, row_count: data.row_count };
                showToast(`Cached ${data.row_count.toLocaleString()} rows from ${_section.table}`);
            } catch (err) {
                showToast('Sync failed: ' + err, true);
            } finally {
                updateCacheBar();
            }
        });
    }

    async function refreshSectionTables() {
        const name = _section.source;
        if (!name) return;
        let items = tablesCache.get(name);
        if (!items) {
            setSectionStatus('Loading tables and views…');
            try {
                const res = await fetch('/api/connections/' + encodeURIComponent(name) + '/tables');
                const data = await res.json().catch(() => ({}));
                if (!res.ok) throw new Error(data.error || res.statusText);
                items = (data.tables || []).map((t) =>
                    typeof t === 'string' ? { name: t, kind: 'table' } : t
                );
                tablesCache.set(name, items);
            } catch (err) {
                setSectionStatus('Tables failed: ' + err.message, 'err');
                return;
            }
        }
        const ts = tableSel();
        ts.innerHTML = '<option value="">-- pick a table or view --</option>';
        const tables = items.filter((i) => i.kind !== 'view');
        const views = items.filter((i) => i.kind === 'view');
        const addGroup = (label, group) => {
            if (!group.length) return;
            const og = document.createElement('optgroup');
            og.label = label;
            group.forEach((i) => og.appendChild(new Option(i.name, i.name)));
            ts.appendChild(og);
        };
        addGroup(`Tables (${tables.length})`, tables);
        addGroup(`Views (${views.length})`, views);
        if (_section.table && items.some((i) => i.name === _section.table)) {
            ts.value = _section.table;
        }
        const counts = [];
        if (tables.length) counts.push(`${tables.length} table${tables.length === 1 ? '' : 's'}`);
        if (views.length) counts.push(`${views.length} view${views.length === 1 ? '' : 's'}`);
        setSectionStatus(counts.length ? `Loaded ${counts.join(' + ')}` : 'No tables found', 'ok');
        if (ts.value) await refreshSectionColumns();
    }

    async function refreshSectionColumns() {
        if (!_section.source || !_section.table) {
            _section.columns = [];
            return;
        }
        const cacheKey = _section.source + '::' + _section.table;
        let cols = columnsCache.get(cacheKey);
        if (!cols) {
            try {
                const res = await fetch('/api/connections/' + encodeURIComponent(_section.source) +
                    '/columns?table=' + encodeURIComponent(_section.table));
                const data = await res.json().catch(() => ({}));
                if (!res.ok) throw new Error(data.error || res.statusText);
                cols = data.columns || [];
                columnsCache.set(cacheKey, cols);
            } catch (err) {
                setSectionStatus('Columns failed: ' + err.message, 'err');
                return;
            }
        }
        _section.columns = cols;
    }

    // ------------------------------------------------------------------
    // Field-keys datalist (autocomplete for the "Fills label field" input)
    // ------------------------------------------------------------------

    function refreshFieldKeysDatalist() {
        let dl = document.getElementById('dbFieldKeysDataList');
        if (!dl) {
            dl = document.createElement('datalist');
            dl.id = 'dbFieldKeysDataList';
            document.body.appendChild(dl);
        }
        dl.innerHTML = '';
        const keys = new Set();
        [listText(), listDb()].forEach((root) => {
            root.querySelectorAll('[data-attr="key"]').forEach((i) => {
                const k = i.value.trim();
                if (k) keys.add(k);
            });
        });
        keys.forEach((k) => dl.appendChild(new Option(k)));
    }

    // ------------------------------------------------------------------
    // Common card chrome (key/label/default/placeholder/required/multiline)
    // ------------------------------------------------------------------

    function renderCommon(card, spec) {
        const label = card.dataset.kind === 'lookup' ? 'Database lookup' : 'Text field';
        card.innerHTML = `
            <header class="field-card__header">
                <span class="field-card__kind">${label}</span>
                <button type="button" class="field-card__remove" data-action="remove"
                        title="Remove field" aria-label="Remove field">×</button>
            </header>
            <div class="field-card__id-row">
                <label class="stacked">
                    <span>Key <em>identifier in the ZPL</em></span>
                    <input type="text" data-attr="key" placeholder="field_key">
                </label>
                <label class="stacked">
                    <span>Label <em>shown to the user</em></span>
                    <input type="text" data-attr="label" placeholder="Field name">
                </label>
            </div>
            <div class="field-card__props">
                <label class="stacked">
                    <span>Default value</span>
                    <input type="text" data-attr="default" placeholder="(empty)">
                </label>
                <label class="stacked">
                    <span>Placeholder</span>
                    <input type="text" data-attr="placeholder" placeholder="(empty)">
                </label>
            </div>
            <div class="field-card__flags">
                <label class="checkbox-inline">
                    <input type="checkbox" data-attr="required"> Required
                </label>
                <label class="checkbox-inline">
                    <input type="checkbox" data-attr="multiline"> Multiline
                </label>
            </div>
            <div data-slot="extra"></div>
        `;
        card.querySelector('[data-attr="key"]').value = spec.key || '';
        card.querySelector('[data-attr="label"]').value = spec.label || '';
        card.querySelector('[data-attr="default"]').value = spec.default || '';
        card.querySelector('[data-attr="placeholder"]').value = spec.placeholder || '';
        card.querySelector('[data-attr="required"]').checked = !!spec.required;
        card.querySelector('[data-attr="multiline"]').checked = !!spec.multiline;

        card.querySelector('[data-action="remove"]').addEventListener('click', () => {
            card.remove();
            updateSummary();
            refreshFieldKeysDatalist();
            // The remaining DB cards may have hints that referenced this card's key.
            renderAllConfigTables();
        });

        card.querySelector('[data-attr="key"]').addEventListener('input', () => {
            refreshFieldKeysDatalist();
            // Hints "(this lookup's value)" / "(existing field)" might change.
            renderAllConfigTables();
        });
    }

    // ------------------------------------------------------------------
    // Text field card
    // ------------------------------------------------------------------

    function addTextField(spec) {
        spec = spec || {};
        const card = document.createElement('div');
        card.className = 'field-card field-card--text';
        card.dataset.kind = 'text';
        renderCommon(card, spec);
        listText().appendChild(card);
        updateSummary();
        refreshFieldKeysDatalist();
        return card;
    }

    // ------------------------------------------------------------------
    // Database lookup card — single config table per card
    // ------------------------------------------------------------------

    function addDbField(spec) {
        spec = spec || {};
        const card = document.createElement('div');
        card.className = 'field-card field-card--db';
        card.dataset.kind = 'lookup';

        // _roles holds per-card role assignments; column → set membership / fills target
        card._roles = {
            search: new Set(spec.search_columns || []),
            display: new Set(spec.display_columns || []),
            fills: {},  // column -> field_key
        };
        // value_column: maps onto fills[value_column] = card.key
        if (spec.value_column && spec.key) {
            card._roles.fills[spec.value_column] = spec.key;
        }
        // autofill is stored as {field_key: column} → invert into fills[column] = field_key
        if (spec.autofill && typeof spec.autofill === 'object') {
            Object.entries(spec.autofill).forEach(([fk, col]) => {
                card._roles.fills[col] = fk;
            });
        }

        renderCommon(card, spec);
        const slot = card.querySelector('[data-slot="extra"]');
        slot.innerHTML = `
            <section class="lookup-panel" aria-label="Database lookup configuration">
                <header class="lookup-panel__header">
                    <h4>How this lookup works</h4>
                    <p>Tick which role each column plays. The "Fills label field" column either points
                       at this lookup itself, an existing text field, or a brand-new field name —
                       new names get a text field auto-created on save.</p>
                </header>
                <div class="lookup-config-wrap">
                    <table class="lookup-config-table">
                        <thead>
                            <tr>
                                <th>Column</th>
                                <th>Search</th>
                                <th>In popup</th>
                                <th>Fills label field</th>
                            </tr>
                        </thead>
                        <tbody data-role="config-table"></tbody>
                    </table>
                </div>
            </section>
        `;

        listDb().appendChild(card);
        renderConfigTable(card);
        updateSummary();
        refreshFieldKeysDatalist();
        return card;
    }

    function renderConfigTable(card) {
        const tbody = card.querySelector('[data-role="config-table"]');
        if (!tbody) return;

        const cols = _section.columns.slice();
        // Keep saved-but-not-yet-loaded columns visible
        const ensure = (xs) => xs.forEach((c) => { if (c && !cols.includes(c)) cols.push(c); });
        ensure(Array.from(card._roles.search));
        ensure(Array.from(card._roles.display));
        ensure(Object.keys(card._roles.fills));

        tbody.innerHTML = '';

        if (!_section.source || !_section.table) {
            const tr = document.createElement('tr');
            tr.innerHTML = `<td colspan="4" class="muted">
                Pick a connection and table above to load this template's columns.
            </td>`;
            tbody.appendChild(tr);
            return;
        }
        if (!cols.length) {
            const tr = document.createElement('tr');
            tr.innerHTML = `<td colspan="4" class="muted">No columns reported for this table.</td>`;
            tbody.appendChild(tr);
            return;
        }

        const myKey = (card.querySelector('[data-attr="key"]').value || '').trim();
        const existingKeys = collectExistingKeys();

        cols.forEach((col) => {
            const tr = document.createElement('tr');
            tr.dataset.col = col;
            tr.innerHTML = `
                <td><code>${col}</code></td>
                <td class="cell-cb"><input type="checkbox" data-role="search" aria-label="Use ${col} as a search column"></td>
                <td class="cell-cb"><input type="checkbox" data-role="display" aria-label="Show ${col} in popup"></td>
                <td class="cell-fills">
                    <input type="text" data-role="fills" placeholder="(don't fill)"
                           list="dbFieldKeysDataList" autocomplete="off"
                           aria-label="Field key that gets the ${col} value">
                    <span class="fills-hint"></span>
                </td>
            `;
            const cb1 = tr.querySelector('[data-role="search"]');
            const cb2 = tr.querySelector('[data-role="display"]');
            const fi = tr.querySelector('[data-role="fills"]');

            cb1.checked = card._roles.search.has(col);
            cb2.checked = card._roles.display.has(col);
            fi.value = card._roles.fills[col] || '';

            cb1.addEventListener('change', () => {
                if (cb1.checked) card._roles.search.add(col);
                else card._roles.search.delete(col);
            });
            cb2.addEventListener('change', () => {
                if (cb2.checked) card._roles.display.add(col);
                else card._roles.display.delete(col);
            });
            fi.addEventListener('input', () => {
                const v = fi.value.trim();
                if (v) card._roles.fills[col] = v;
                else delete card._roles.fills[col];
                updateFillsHint(tr, fi.value.trim(), myKey, existingKeys);
            });

            updateFillsHint(tr, fi.value.trim(), myKey, existingKeys);
            tbody.appendChild(tr);
        });
    }

    function updateFillsHint(tr, value, myKey, existingKeys) {
        const hint = tr.querySelector('.fills-hint');
        if (!hint) return;
        hint.classList.remove('fills-hint--this', 'fills-hint--new', 'fills-hint--existing');
        if (!value) {
            hint.textContent = '';
            return;
        }
        if (myKey && value === myKey) {
            hint.textContent = "this lookup's value";
            hint.classList.add('fills-hint--this');
            return;
        }
        if (existingKeys.has(value)) {
            hint.textContent = 'existing field';
            hint.classList.add('fills-hint--existing');
            return;
        }
        hint.textContent = 'new — created on save';
        hint.classList.add('fills-hint--new');
    }

    function collectExistingKeys() {
        const keys = new Set();
        [listText(), listDb()].forEach((root) => {
            root.querySelectorAll('[data-attr="key"]').forEach((i) => {
                const k = i.value.trim();
                if (k) keys.add(k);
            });
        });
        return keys;
    }

    function renderAllConfigTables() {
        listDb().querySelectorAll('.field-card').forEach((c) => renderConfigTable(c));
    }

    // ------------------------------------------------------------------
    // Save / reset
    // ------------------------------------------------------------------

    function baseSpec(card) {
        return {
            key: card.querySelector('[data-attr="key"]').value.trim(),
            label: card.querySelector('[data-attr="label"]').value.trim(),
            default: card.querySelector('[data-attr="default"]').value,
            placeholder: card.querySelector('[data-attr="placeholder"]').value,
            required: card.querySelector('[data-attr="required"]').checked,
            multiline: card.querySelector('[data-attr="multiline"]').checked,
        };
    }

    function humanise(key) {
        return (key || '')
            .split(/[_\s]+/)
            .filter(Boolean)
            .map((s) => s.charAt(0).toUpperCase() + s.slice(1))
            .join(' ');
    }

    function gatherFields() {
        const out = [];

        listDb().querySelectorAll('.field-card').forEach((card) => {
            const f = baseSpec(card);
            f.type = 'lookup';
            f.source = _section.source || '';
            f.table = _section.table || '';

            const search = [];
            const display = [];
            let value = '';
            const autofill = {};

            card._roles.search.forEach((c) => search.push(c));
            card._roles.display.forEach((c) => display.push(c));

            Object.entries(card._roles.fills).forEach(([col, fk]) => {
                if (!fk) return;
                if (fk === f.key) value = col;
                else autofill[fk] = col;
            });

            f.search_columns = search;
            f.display_columns = display;
            f.value_column = value;
            f.autofill = autofill;
            out.push(f);
        });

        listText().querySelectorAll('.field-card').forEach((card) => {
            const f = baseSpec(card);
            f.type = 'text';
            out.push(f);
        });

        // Auto-create text fields for any autofill target that doesn't exist
        const existing = new Set(out.map((f) => f.key));
        out.filter((f) => f.type === 'lookup').forEach((lookup) => {
            Object.keys(lookup.autofill || {}).forEach((key) => {
                if (existing.has(key)) return;
                out.push({
                    key,
                    label: humanise(key),
                    default: '',
                    placeholder: '',
                    required: false,
                    multiline: false,
                    type: 'text',
                });
                existing.add(key);
            });
        });

        return out;
    }

    async function saveFields() {
        const fields = gatherFields();
        if (fields.some((f) => !f.key)) {
            showToast('Every field needs a key.', true);
            return;
        }
        const file = templateFile();
        await withBusy($('fieldsSave'), async () => {
            try {
                const res = await fetch('/config/fields/' + encodeURIComponent(file), {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ fields }),
                });
                const data = await res.json().catch(() => ({}));
                if (!res.ok || !data.ok) {
                    showToast(data.error || 'Save failed', true);
                    return;
                }
                showToast('Saved ' + file);
                editor().dataset.fields = JSON.stringify(data.fields);
                editor().dataset.hasSidecar = '1';
                markClean();
                renderAll();
            } catch (err) {
                showToast('Save failed: ' + err, true);
            }
        });
    }

    async function resetFields() {
        if (!confirm('Remove the sidecar and revert to auto-detected fields?')) return;
        const file = templateFile();
        try {
            const res = await fetch('/config/fields/' + encodeURIComponent(file), { method: 'DELETE' });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) { showToast(data.error || 'Reset failed', true); return; }
            const refresh = await fetch('/config/fields/' + encodeURIComponent(file));
            const fresh = await refresh.json().catch(() => ({}));
            editor().dataset.fields = JSON.stringify(fresh.fields || []);
            editor().dataset.hasSidecar = fresh.has_sidecar ? '1' : '0';
            showToast('Reverted to auto-detected fields');
            renderAll();
        } catch (err) {
            showToast('Reset failed: ' + err, true);
        }
    }

    // ------------------------------------------------------------------
    // Mount
    // ------------------------------------------------------------------

    function updateSummary() {
        const dbCount = listDb().querySelectorAll('.field-card').length;
        const textCount = listText().querySelectorAll('.field-card').length;
        const total = dbCount + textCount;
        const sidecar = editor().dataset.hasSidecar === '1' ? 'sidecar customised' : 'auto-detected from ZPL';
        if (!total) {
            summary().textContent = 'No fields yet · ' + sidecar;
            return;
        }
        const parts = [];
        if (dbCount) parts.push(`${dbCount} database lookup${dbCount === 1 ? '' : 's'}`);
        if (textCount) parts.push(`${textCount} text`);
        summary().textContent = parts.join(' · ') + ' · ' + sidecar;
    }

    async function renderAll() {
        listText().innerHTML = '';
        listDb().innerHTML = '';

        let specs = [];
        try { specs = JSON.parse(editor().dataset.fields || '[]'); } catch (e) { /* ignore */ }

        // Derive section source + table from the first lookup field, if any
        const firstLookup = specs.find((s) => s.type === 'lookup');
        if (firstLookup) {
            _section.source = firstLookup.source || '';
            _section.table = firstLookup.table || '';
        }

        initSectionControls();

        if (_section.source) {
            await refreshSectionTables();
        }
        if (_section.source && _section.table) {
            await refreshCacheMeta();
        }

        specs.forEach((spec) => {
            if (spec.type === 'lookup') addDbField(spec);
            else addTextField(spec);
        });
        renderAllConfigTables();
        updateSummary();
        refreshFieldKeysDatalist();
        updateCacheBar();
    }

    document.addEventListener('DOMContentLoaded', () => {
        if (!editor()) return;
        renderAll();
        $('fieldsAddText').addEventListener('click', () => { addTextField(); markDirty(); });
        $('fieldsAddDb').addEventListener('click', () => { addDbField(); markDirty(); });
        $('fieldsSave').addEventListener('click', saveFields);
        $('fieldsReset').addEventListener('click', resetFields);

        // Any input/change in the editor counts as a pending edit.
        editor().addEventListener('input', markDirty);
        editor().addEventListener('change', markDirty);

        // Cmd/Ctrl + S triggers Save.
        document.addEventListener('keydown', (e) => {
            const isSave = (e.metaKey || e.ctrlKey) && (e.key === 's' || e.key === 'S');
            if (isSave) {
                e.preventDefault();
                saveFields();
            }
        });
    });
})();
