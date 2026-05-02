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
        try {
            const res = await fetch('/api/fields/' + encodeURIComponent(tpl.value));
            if (!res.ok) { showToast('Could not load template fields', true); return; }
            const data = await res.json();
            renderFields(data.fields || [], tpl.value);
            // Pre-fill the per-job overrides with the template's stored
            // defaults so the user sees what would be sent if they don't
            // touch anything (and so per-tab restoration has a sane baseline).
            applyPrintSettings(data.print_settings || {});
        } catch (err) {
            showToast('Failed to fetch fields: ' + err, true);
        }
    }

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
            const val = lastMeta.value_column ? row_data[lastMeta.value_column] : '';
            input.value = val == null ? '' : String(val);
            // Autofill other fields
            Object.entries(lastMeta.autofill || {}).forEach(([targetKey, dbCol]) => {
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

        function render(rows, meta, error) {
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
            setActive(0);
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
                render(lastRows, lastMeta);
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

    document.addEventListener('DOMContentLoaded', () => {
        const p = previewForm();
        const l = labelForm();
        if (!p || !l) return;
        p.addEventListener('input', syncMirrorAndPreview);
        const tpl = document.getElementById('template_file');
        if (tpl) tpl.addEventListener('change', onTemplateChange);
        syncMirrorAndPreview();
        attachLookups();
        p.addEventListener('submit', submitPreview);
        l.addEventListener('submit', submitPrint);
    });
})();
