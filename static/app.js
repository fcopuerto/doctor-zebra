(function () {
    'use strict';

    const previewForm = () => document.getElementById('previewForm');
    const labelForm = () => document.getElementById('labelForm');
    const container = () => document.getElementById('fieldsContainer');
    const mirror = () => document.getElementById('labelHiddenMirror');
    const previewValues = () => document.getElementById('previewValues');

    function showToast(msg, isError) {
        const toast = document.getElementById('toast');
        if (!toast) return;
        toast.textContent = msg;
        toast.classList.toggle('error', !!isError);
        toast.style.display = 'block';
        clearTimeout(showToast._timer);
        showToast._timer = setTimeout(() => { toast.style.display = 'none'; }, 3000);
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

    function formatCacheAge(iso) {
        if (!iso) return '';
        const t = Date.parse(iso);
        if (isNaN(t)) return '';
        const min = Math.max(0, Math.round((Date.now() - t) / 60000));
        if (min < 1) return 'menos de 1 min';
        if (min < 60) return min + ' min';
        const h = Math.round(min / 60);
        if (h < 24) return h + ' h';
        return Math.round(h / 24) + ' d';
    }

    function currentFields() {
        return Array.from(container().querySelectorAll('[data-field-key]')).map((row) => ({
            key: row.dataset.fieldKey,
            el: row.querySelector('input, textarea'),
        }));
    }

    function syncMirrorAndPreview() {
        const fields = currentFields();
        const m = mirror();
        const pv = previewValues();
        m.innerHTML = '';
        pv.innerHTML = '';
        fields.forEach(({ key, el }) => {
            const val = el ? el.value : '';
            const hidden = document.createElement('input');
            hidden.type = 'hidden'; hidden.name = key; hidden.value = val;
            m.appendChild(hidden);

            const labelEl = el ? el.closest('.field-row').querySelector('label') : null;
            const labelText = labelEl
                ? labelEl.textContent.replace('*', '').replace(/\s+DB lookup\s*$/i, '').trim()
                : key;
            const line = document.createElement('div');
            line.className = 'preview-line';
            line.dataset.previewKey = key;
            line.innerHTML = `<strong></strong> <span></span>`;
            line.querySelector('strong').textContent = labelText + ':';
            line.querySelector('span').textContent = val;
            pv.appendChild(line);
        });

        const tpl = document.getElementById('template_file');
        const tplLabel = document.getElementById('preview_template');
        if (tpl && tplLabel) tplLabel.textContent = tpl.value;
        const hiddenTpl = labelForm().querySelector('input[name="template_file"]');
        if (hiddenTpl && tpl) hiddenTpl.value = tpl.value;
    }

    // ------------------------------------------------------------------
    // Field rendering (used after a template change)
    // ------------------------------------------------------------------

    function renderFields(specs, templateFile) {
        const c = container();
        c.dataset.template = templateFile || '';
        c.innerHTML = '';
        if (!specs || !specs.length) {
            const p = document.createElement('p');
            p.className = 'muted'; p.id = 'noFieldsHint';
            p.textContent = 'This template has no editable fields. Press Print to send it as-is.';
            c.appendChild(p);
            syncMirrorAndPreview();
            return;
        }
        specs.forEach((f) => {
            const row = document.createElement('div');
            const isLookup = f.type === 'lookup' && !f.multiline;
            row.className = 'field-row' + (isLookup ? ' has-lookup' : '');
            row.dataset.fieldKey = f.key;
            row.dataset.fieldType = f.type || 'text';
            if (isLookup) row.dataset.searchColumns = (f.search_columns || []).join(',');

            const label = document.createElement('label');
            label.htmlFor = 'field_' + f.key;
            label.textContent = f.label || f.key;
            if (f.required) {
                const star = document.createElement('span');
                star.className = 'req'; star.textContent = '*';
                label.appendChild(star);
            }
            if (f.barcode) {
                const b = document.createElement('span');
                b.className = 'badge'; b.textContent = f.barcode;
                label.appendChild(document.createTextNode(' '));
                label.appendChild(b);
            }

            let input;
            if (f.multiline) {
                input = document.createElement('textarea');
                input.rows = 3;
            } else {
                input = document.createElement('input');
                input.type = 'text';
                if (isLookup) input.autocomplete = 'off';
            }
            input.id = 'field_' + f.key;
            input.name = f.key;
            input.value = f.default || '';
            const cols = (f.search_columns || []).filter(Boolean);
            const lookupPlaceholder = cols.length
                ? 'Starts with… (use * for any) — ' + cols.join(', ')
                : 'Starts with… (use * for any)';
            input.placeholder = f.placeholder || (isLookup ? lookupPlaceholder : '');
            if (f.required) input.required = true;

            row.appendChild(label);

            if (isLookup) {
                const wrap = document.createElement('div');
                wrap.className = 'lookup-input';
                const icon = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
                icon.classList.add('lookup-input__icon');
                icon.setAttribute('aria-hidden', 'true');
                const use = document.createElementNS('http://www.w3.org/2000/svg', 'use');
                use.setAttribute('href', '#i-search');
                icon.appendChild(use);
                wrap.appendChild(icon);
                wrap.appendChild(input);
                const dd = document.createElement('div');
                dd.className = 'lookup-results';
                dd.hidden = true;
                wrap.appendChild(dd);
                row.appendChild(wrap);
            } else {
                row.appendChild(input);
            }

            c.appendChild(row);
        });
        syncMirrorAndPreview();
        attachLookups();
        // Let other modules (e.g. print-tabs.js) know the form has been
        // rebuilt, so they can restore per-tab state into the new inputs.
        c.dispatchEvent(new CustomEvent('fields:rendered', {
            bubbles: true,
            detail: { template: templateFile || '' },
        }));
    }

    async function onTemplateChange() {
        const tpl = document.getElementById('template_file');
        if (!tpl || !tpl.value) return;
        // Reload the version dropdown for the new template, then load
        // fields for whichever version is selected.
        await refreshVersionDropdown(tpl.value);
        await loadFieldsForCurrentVersion();
    }

    async function refreshVersionDropdown(templateFile) {
        const sel = document.getElementById('template_version');
        if (!sel) return;
        // Default option is always "current"; saved versions get
        // appended in newest-first order.
        sel.innerHTML = '<option value="current">— current —</option>';
        try {
            const r = await fetch('/api/templates/' + encodeURIComponent(templateFile) + '/versions');
            if (!r.ok) return;
            const data = await r.json();
            (data.versions || []).forEach(v => {
                const opt = document.createElement('option');
                opt.value = v.timestamp;
                opt.textContent = 'v' + v.version + ' · ' + (v.ts_human || v.timestamp);
                sel.appendChild(opt);
            });
        } catch (e) { /* offline → only current */ }
    }

    async function loadFieldsForCurrentVersion() {
        const tpl = document.getElementById('template_file');
        const ver = document.getElementById('template_version');
        const hiddenVer = document.getElementById('labelVersionTs');
        if (!tpl || !tpl.value) return;
        const versionTs = (ver && ver.value) || 'current';
        if (hiddenVer) hiddenVer.value = versionTs;
        const url = '/api/fields/' + encodeURIComponent(tpl.value) +
            (versionTs && versionTs !== 'current' ? '?version=' + encodeURIComponent(versionTs) : '');
        try {
            const res = await fetch(url);
            if (!res.ok) { showToast('Could not load template fields', true); return; }
            const data = await res.json();
            renderFields(data.fields || [], tpl.value);
            applyPrintSettings(data.print_settings || {});
        } catch (err) {
            showToast('Failed to fetch fields: ' + err, true);
        }
    }

    // Wire the version selector to reload fields when the user changes it.
    document.addEventListener('DOMContentLoaded', () => {
        const ver = document.getElementById('template_version');
        if (ver) ver.addEventListener('change', loadFieldsForCurrentVersion);
        // First-load: populate dropdown for the initial template.
        const tpl = document.getElementById('template_file');
        if (tpl && tpl.value) refreshVersionDropdown(tpl.value);
    });

    function applyPrintSettings(ps) {
        // Media type
        const mt = (ps.media_type || '').toLowerCase();
        document.querySelectorAll('input[name="media_type"]').forEach((r) => {
            r.checked = (r.value === mt) || (mt === '' && r.value === '');
        });
        // Speed
        const sp = document.getElementById('job_speed');
        if (sp) sp.value = parseInt(ps.speed_ips, 10) || 0;
        // Darkness
        const dk = document.getElementById('job_darkness');
        if (dk) {
            const v = (ps.darkness === undefined || ps.darkness === null) ? -1 : parseInt(ps.darkness, 10);
            dk.value = isNaN(v) ? -1 : v;
            const lbl = document.getElementById('job_darkness_value');
            if (lbl) lbl.textContent = dk.value < 0 ? '—' : dk.value;
        }
    }

    // ------------------------------------------------------------------
    // Lookup autocomplete
    // ------------------------------------------------------------------

    function attachLookups() {
        document.querySelectorAll('[data-field-type="lookup"]').forEach(setupLookup);
    }

    function setupLookup(row) {
        if (row._lookupReady) return;
        row._lookupReady = true;
        const input = row.querySelector('input[type="text"]');
        const results = row.querySelector('.lookup-results');
        const tpl = container().dataset.template;
        const key = row.dataset.fieldKey;
        if (!input || !results || !tpl || !key) return;

        const wrap = input.closest('.lookup-input');
        const statusEl = document.createElement('div');
        statusEl.className = 'lookup-status';
        statusEl.hidden = true;
        if (wrap) wrap.appendChild(statusEl);

        function updateConnectionStatus(cache) {
            if (!cache || cache.connection_status !== 'offline') {
                statusEl.hidden = true;
                return;
            }
            const age = formatCacheAge(cache.last_sync);
            const reason = (cache.last_failure && cache.last_failure.error) || '';
            statusEl.title = reason
                ? 'Último error: ' + reason
                : 'No se ha podido contactar con la BD en el último intento.';
            const tail = cache.row_count
                ? ' · usando cache' + (age ? ' de hace ' + age : '')
                : ' · sin caché — escribe el valor manualmente';
            statusEl.innerHTML = '<span class="lookup-status__dot"></span>'
                + 'BD no accesible' + tail;
            statusEl.hidden = false;
        }

        let timer = null;
        let activeIdx = -1;
        let lastRows = [];
        let lastMeta = { value_column: '', autofill: {}, display_columns: [] };

        function close() {
            results.hidden = true;
            results.innerHTML = '';
            activeIdx = -1;
        }

        function setActive(idx) {
            results.querySelectorAll('.lookup-result').forEach((el, i) => {
                el.classList.toggle('active', i === idx);
            });
            activeIdx = idx;
        }

        function pick(row_data) {
            // value_column is the canonical target for the lookup input
            // itself. If the user didn't configure one, fall back to:
            //  1) the autofill entry pointing at this same field (covers
            //     the common pattern of separate lookup + visible field),
            //  2) the first display column,
            // so picking never wipes the input to empty.
            const af = lastMeta.autofill || {};
            let val = lastMeta.value_column ? row_data[lastMeta.value_column] : null;
            if (val == null && af[key]) val = row_data[af[key]];
            if (val == null && lastMeta.display_columns && lastMeta.display_columns.length) {
                val = row_data[lastMeta.display_columns[0]];
            }
            if (val != null) input.value = String(val);

            // Autofill other fields
            Object.entries(af).forEach(([targetKey, dbCol]) => {
                const targetRow = container().querySelector(`[data-field-key="${CSS.escape(targetKey)}"]`);
                if (!targetRow) return;
                const targetInput = targetRow.querySelector('input, textarea');
                if (!targetInput) return;
                const v = row_data[dbCol];
                targetInput.value = v == null ? '' : String(v);
            });
            close();
            syncMirrorAndPreview();
            input.dispatchEvent(new Event('change', { bubbles: true }));
        }

        function render(rows, meta, error, isLive) {
            results.innerHTML = '';
            if (error) {
                const e = document.createElement('div');
                e.className = 'lookup-empty'; e.textContent = error;
                results.appendChild(e);
                results.hidden = false;
                return;
            }
            if (!rows.length) {
                const e = document.createElement('div');
                e.className = 'lookup-empty'; e.textContent = 'No results';
                results.appendChild(e);
                results.hidden = false;
                return;
            }
            if (isLive) {
                const tag = document.createElement('div');
                tag.className = 'lookup-empty lookup-empty--live';
                tag.textContent = 'Resultados en vivo desde la BD';
                results.appendChild(tag);
            }
            const cols = meta.display_columns && meta.display_columns.length
                ? meta.display_columns
                : Object.keys(rows[0]);
            rows.forEach((r, i) => {
                const item = document.createElement('div');
                item.className = 'lookup-result';
                const head = cols[0];
                const tail = cols.slice(1);
                item.innerHTML = `<div class="key"></div>${tail.length ? '<div class="meta"></div>' : ''}`;
                item.querySelector('.key').textContent = head ? String(r[head] ?? '') : '';
                if (tail.length) {
                    item.querySelector('.meta').textContent = tail
                        .map((c) => `${c}: ${r[c] == null ? '' : r[c]}`).join(' · ');
                }
                item.addEventListener('mousedown', (e) => { e.preventDefault(); pick(r); });
                results.appendChild(item);
            });
            results.hidden = false;
            // No auto-highlight on first row — Enter would otherwise replace
            // the user's typed query with that row's value silently. The
            // user opts in by ArrowDown or by clicking.
            activeIdx = -1;
        }

        let _syncRetryTimer = null;

        async function search(q) {
            try {
                const res = await fetch(
                    '/api/lookup/' + encodeURIComponent(tpl) + '/' + encodeURIComponent(key)
                    + '?q=' + encodeURIComponent(q),
                );
                const data = await res.json().catch(() => ({}));
                if (!res.ok) { render([], {}, data.error || 'Lookup failed'); return; }
                updateConnectionStatus(data.cache);
                if (data.no_cache) {
                    renderNoCache();
                    return;
                }
                if (data.syncing) {
                    renderSyncing(q);
                    return;
                }
                if (data.warning) { renderWarning(data.warning); return; }
                clearTimeout(_syncRetryTimer);
                lastRows = data.rows || [];
                lastMeta = {
                    value_column: data.value_column || '',
                    autofill: data.autofill || {},
                    display_columns: data.display_columns || [],
                };
                render(lastRows, lastMeta, '', !!data.live);
            } catch (err) {
                render([], {}, 'Lookup failed: ' + err);
            }
        }

        function renderSyncing(q) {
            results.innerHTML = '';
            const w = document.createElement('div');
            w.className = 'lookup-empty lookup-empty--syncing';
            w.innerHTML = `<span class="lookup-spinner"></span>
                Cache is being prepared in the background. Retrying…`;
            results.appendChild(w);
            results.hidden = false;
            clearTimeout(_syncRetryTimer);
            _syncRetryTimer = setTimeout(() => {
                if (input.value.trim() === q) search(q);
            }, 3000);
        }

        function renderNoCache() {
            results.innerHTML = '';
            const w = document.createElement('div');
            w.className = 'lookup-empty lookup-empty--warn';
            w.innerHTML = 'No hay caché disponible y la BD no responde. '
                + 'Puedes escribir el valor directamente y seguir imprimiendo.';
            results.appendChild(w);
            results.hidden = false;
            clearTimeout(_syncRetryTimer);
        }

        function renderWarning(msg) {
            results.innerHTML = '';
            const w = document.createElement('div');
            w.className = 'lookup-empty lookup-empty--warn';
            const tplName = (tpl || '').replace(/\.zpl$/, '');
            w.innerHTML = `${msg} <a href="/templates/${encodeURIComponent(tplName)}/fields"
                target="_blank" rel="noopener">Open the fields editor →</a>`;
            results.appendChild(w);
            results.hidden = false;
        }

        function showFocusHint() {
            const cols = (row.dataset.searchColumns || '')
                .split(',').map((s) => s.trim()).filter(Boolean);
            const target = cols.length ? cols.join(', ') : 'the database';
            results.innerHTML = `
                <div class="lookup-empty lookup-empty--hint">
                    <strong>Starts with</strong> match against ${target}.<br>
                    Use <code>*</code> for wildcards: <code>*foo</code>, <code>*foo*</code>, <code>fo*ar</code>.
                </div>`;
            results.hidden = false;
        }

        input.addEventListener('input', () => {
            const q = input.value.trim();
            clearTimeout(timer);
            if (q.length < 1) { showFocusHint(); return; }
            timer = setTimeout(() => search(q), 250);
        });

        input.addEventListener('focus', () => {
            if (!input.value.trim()) showFocusHint();
        });

        input.addEventListener('keydown', (e) => {
            if (results.hidden) return;
            const items = results.querySelectorAll('.lookup-result');
            if (!items.length) return;
            if (e.key === 'ArrowDown') { e.preventDefault(); setActive(Math.min(items.length - 1, activeIdx + 1)); }
            else if (e.key === 'ArrowUp') { e.preventDefault(); setActive(Math.max(0, activeIdx - 1)); }
            else if (e.key === 'Enter' && activeIdx >= 0) { e.preventDefault(); pick(lastRows[activeIdx]); }
            else if (e.key === 'Escape') { close(); }
        });

        input.addEventListener('blur', () => setTimeout(close, 120));
    }

    // ------------------------------------------------------------------
    // Preview / Print
    // ------------------------------------------------------------------

    function updatePreviewImage(url) {
        const holder = document.getElementById('preview_image_holder');
        if (!holder) return;
        if (url) {
            holder.innerHTML = '';
            const img = document.createElement('img');
            img.src = url; img.alt = 'Label Preview'; img.className = 'label-preview-img';
            holder.appendChild(img);
        } else {
            holder.innerHTML = '<p>Error generating preview.</p>';
        }
    }

    async function submitPreview(e) {
        e.preventDefault();
        const form = e.target;
        const btn = form.querySelector('button[type="submit"]');
        await withBusy(btn, async () => {
            try {
                const res = await fetch(form.action, { method: 'POST', body: new FormData(form) });
                const data = await res.json();
                if (!res.ok) { showToast(data.error || 'Failed to preview label.', true); return; }
                updatePreviewImage(data.image_url);
                showToast('Label preview ready');
            } catch (err) {
                showToast('Failed to preview label.', true);
            }
        });
    }

    // Auto-preview: fire whenever the form changes, debounced to avoid
    // hammering Labelary. Empty fields render as `{key}` server-side so
    // the layout is visible before the user types anything.
    let _autoPreviewKey = '';
    let _autoPreviewTimer = null;
    let _autoPreviewInFlight = false;
    async function autoPreview() {
        const form = previewForm();
        if (!form) return;
        const fd = new FormData(form);
        const entries = [];
        fd.forEach((v, k) => entries.push(k + '=' + v));
        const key = entries.sort().join('&');
        if (key === _autoPreviewKey) return;        // nothing changed
        if (_autoPreviewInFlight) return;            // wait for the in-flight one
        _autoPreviewKey = key;
        _autoPreviewInFlight = true;
        try {
            const res = await fetch(form.action, { method: 'POST', body: fd });
            if (!res.ok) return;
            const data = await res.json();
            if (data.image_url) updatePreviewImage(data.image_url);
        } catch (err) { /* silent — manual button still works */ }
        finally {
            _autoPreviewInFlight = false;
            // If something changed mid-flight, re-fire once.
            schedulePreview();
        }
    }
    function schedulePreview(immediate) {
        clearTimeout(_autoPreviewTimer);
        _autoPreviewTimer = setTimeout(autoPreview, immediate ? 0 : 600);
    }

    async function submitPrint(e) {
        e.preventDefault();
        const form = e.target;
        const btn = form.querySelector('button[type="submit"]');
        await withBusy(btn, async () => {
            try {
                const res = await fetch(form.action, { method: 'POST', body: new FormData(form) });
                const data = await res.json().catch(() => ({}));
                showToast(data.message || 'Label sent to printer!', !res.ok);
            } catch (err) {
                showToast('Failed to print label.', true);
            }
        });
    }

    async function downloadPreview() {
        const img = document.querySelector('#preview_image_holder img.label-preview-img');
        if (!img || !img.src) {
            showToast('No hay preview todavía — espera a que se genere.', true);
            return;
        }
        try {
            const res = await fetch(img.src, { cache: 'no-store' });
            if (!res.ok) throw new Error('HTTP ' + res.status);
            const blob = await res.blob();
            const url = URL.createObjectURL(blob);
            const tpl = document.getElementById('template_file');
            const name = (tpl && tpl.value || 'label').replace(/\.zpl$/i, '');
            const ts = new Date().toISOString().replace(/[:T]/g, '-').slice(0, 19);
            const a = document.createElement('a');
            a.href = url; a.download = `${name}_${ts}.png`;
            document.body.appendChild(a); a.click();
            document.body.removeChild(a);
            setTimeout(() => URL.revokeObjectURL(url), 1000);
        } catch (err) {
            showToast('No se pudo descargar: ' + err, true);
        }
    }

    document.addEventListener('DOMContentLoaded', () => {
        const p = previewForm();
        const l = labelForm();
        if (!p || !l) return;
        p.addEventListener('input', () => { syncMirrorAndPreview(); schedulePreview(); });
        const tpl = document.getElementById('template_file');
        if (tpl) tpl.addEventListener('change', onTemplateChange);
        syncMirrorAndPreview();
        attachLookups();
        p.addEventListener('submit', submitPreview);
        l.addEventListener('submit', submitPrint);
        const dl = document.getElementById('downloadPreviewBtn');
        if (dl) dl.addEventListener('click', downloadPreview);
        // Re-render the preview every time the field set is rebuilt
        // (template change, version change, tab activate).
        const fc = container();
        if (fc) fc.addEventListener('fields:rendered', () => schedulePreview());
        // First paint right after load so the user always sees something.
        schedulePreview(true);
    });
})();
