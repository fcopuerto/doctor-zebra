/* In-page version history.
 *
 * Lives as a card on the Edit Template page. Lists every snapshot,
 * lets the user expand any row to see its ZPL inline, restore a
 * version (snapshots the live state first so the restore is itself
 * reversible), and compare any two refs (including "current") with a
 * unified diff rendered right above the list.
 */
(function () {
    'use strict';

    const I18N = window.VERSIONS_I18N || {};
    const TEMPLATE = window.TEMPLATE_NAME || '';

    const $ = (id) => document.getElementById(id);

    function showResult(msg, isError) {
        const el = $('versionsResult');
        if (!el) return;
        el.textContent = msg || '';
        el.className = 'test-result' + (isError ? ' error' : ' ok');
    }

    let versionsCache = [];

    async function loadAll() {
        try {
            const r = await fetch('/api/templates/' + encodeURIComponent(TEMPLATE) + '/versions');
            const data = await r.json();
            versionsCache = data.versions || [];
            renderList(versionsCache);
            renderCompareDropdowns(versionsCache);
            renderCounter(versionsCache.length);
        } catch (e) {
            $('versionsList').innerHTML = '<p class="muted">Error: ' + e + '</p>';
        }
    }

    function renderCounter(n) {
        const badge = $('versionsCounter');
        if (!badge) return;
        if (n <= 0) {
            badge.hidden = true;
            return;
        }
        badge.hidden = false;
        const v = $('versionsCounterValue');
        if (v) v.textContent = n;
    }

    function renderList(versions) {
        const list = $('versionsList');
        list.innerHTML = '';
        if (!versions.length) {
            const p = document.createElement('p');
            p.className = 'muted dashboard__empty';
            p.textContent = list.dataset.empty || '';
            list.appendChild(p);
            return;
        }
        versions.forEach((v) => {
            const row = document.createElement('div');
            row.className = 'version-row version-row--inline';
            row.dataset.ts = v.timestamp;
            row.innerHTML = `
                <div class="version-row__head">
                    <button type="button" class="version-row__toggle" aria-expanded="false">▸</button>
                    <div class="version-row__main">
                        <strong></strong>
                        <span class="muted"></span>
                    </div>
                    <div class="version-row__actions">
                        <button type="button" class="btn-ghost" data-action="diff-current">${I18N.compare_with_current || 'vs current'}</button>
                        <button type="button" class="btn-danger" data-action="restore">${I18N.restore_short || 'Restore'}</button>
                    </div>
                </div>
                <div class="version-row__body" hidden>
                    <pre class="net-firewall__manual" data-zpl></pre>
                </div>`;
            row.querySelector('strong').textContent =
                'v' + v.version + ' · ' + (v.ts_human || v.timestamp);
            const meta = (v.size_bytes || 0) + ' B' +
                (v.has_sidecar ? ' · ' + (I18N.has_sidecar || 'with sidecar') : ' · ' + (I18N.no_sidecar || 'no sidecar')) +
                (v.reason ? ' · ' + v.reason : '');
            row.querySelector('.muted').textContent = meta;

            // Toggle expand / collapse
            const toggle = row.querySelector('.version-row__toggle');
            toggle.addEventListener('click', async () => {
                const body = row.querySelector('.version-row__body');
                const expanded = !body.hidden;
                if (expanded) {
                    body.hidden = true;
                    toggle.textContent = '▸';
                    toggle.setAttribute('aria-expanded', 'false');
                } else {
                    const pre = body.querySelector('[data-zpl]');
                    if (!pre.textContent) {
                        pre.textContent = I18N.loading || '…';
                        try {
                            const r = await fetch('/api/templates/' + encodeURIComponent(TEMPLATE) +
                                '/versions/' + v.timestamp);
                            const data = await r.json();
                            pre.textContent = data.zpl || '';
                        } catch (e) {
                            pre.textContent = 'Error: ' + e;
                        }
                    }
                    body.hidden = false;
                    toggle.textContent = '▾';
                    toggle.setAttribute('aria-expanded', 'true');
                }
            });

            row.querySelector('[data-action="diff-current"]').addEventListener('click',
                () => runCompare(v.timestamp, 'current'));
            row.querySelector('[data-action="restore"]').addEventListener('click',
                () => doRestore(v.timestamp));

            list.appendChild(row);
        });
    }

    function renderCompareDropdowns(versions) {
        const a = $('versionsCompareA');
        const b = $('versionsCompareB');
        if (!a || !b) return;
        const opts = ['<option value="current">' + (I18N.current || 'current') + '</option>'];
        versions.forEach((v) => {
            opts.push('<option value="' + v.timestamp + '">v' + v.version + ' · ' +
                      (v.ts_human || v.timestamp) + '</option>');
        });
        a.innerHTML = opts.join('');
        b.innerHTML = opts.join('');
        // Sensible default: newest version on A, current on B
        if (versions.length > 0) a.value = versions[0].timestamp;
        b.value = 'current';
    }

    async function runCompare(a, b) {
        try {
            const r = await fetch(
                '/api/templates/' + encodeURIComponent(TEMPLATE) +
                '/versions/compare?a=' + encodeURIComponent(a) + '&b=' + encodeURIComponent(b));
            const data = await r.json();
            renderDiff(data, a, b);
        } catch (e) {
            showResult('Error: ' + e, true);
        }
    }

    function renderDiff(d, refA, refB) {
        const box = $('versionsDiff');
        box.hidden = false;
        $('versionsDiffTitle').textContent =
            (d.a_label || '?') + '  →  ' + (d.b_label || '?');

        // --- Previews (used by all three visual modes) ---------------
        $('versionsPreviewALabel').textContent = d.a_label || '?';
        $('versionsPreviewBLabel').textContent = d.b_label || '?';
        $('overlaySliderALabel').textContent = d.a_label || 'A';
        $('overlaySliderBLabel').textContent = d.b_label || 'B';
        loadPreviewInto('versionsPreviewA', refA);
        loadPreviewInto('versionsPreviewB', refB);
        // The slider and diff modes share the same image URLs as
        // side-by-side; setting them up front avoids a flash on mode change.
        const urlA = previewUrl(refA);
        const urlB = previewUrl(refB);
        document.getElementById('overlayA').src = urlA;
        document.getElementById('overlayB').src = urlB;
        document.getElementById('diffA').src = urlA;
        document.getElementById('diffB').src = urlB;
        // Reset slider to 50/50 each compare so the user sees both halves.
        const slider = document.getElementById('overlaySlider');
        if (slider) {
            slider.value = 50;
            applySliderValue(50);
        }
        // Default mode after a fresh compare: side-by-side.
        setDiffMode('side');

        // --- Unified diff text ---------------------------------------
        const out = $('versionsDiffBody');
        out.innerHTML = '';
        const lines = d.lines || [];
        if (!lines.length) {
            const p = document.createElement('p');
            p.className = 'muted';
            p.textContent = I18N.no_diff || 'No differences.';
            out.appendChild(p);
        } else {
            lines.forEach((line) => {
                const span = document.createElement('div');
                span.className = 'diff-line';
                if (line.startsWith('+++') || line.startsWith('---')) span.classList.add('diff-meta');
                else if (line.startsWith('@@')) span.classList.add('diff-hunk');
                else if (line.startsWith('+')) span.classList.add('diff-add');
                else if (line.startsWith('-')) span.classList.add('diff-del');
                span.textContent = line;
                out.appendChild(span);
            });
        }
        box.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    function previewUrl(ref) {
        return '/api/templates/' + encodeURIComponent(TEMPLATE) +
            '/preview?ref=' + encodeURIComponent(ref) + '&t=' + Date.now();
    }

    function loadPreviewInto(imgId, ref) {
        const img = document.getElementById(imgId);
        const empty = document.getElementById(imgId + 'Empty');
        if (!img) return;
        const url = previewUrl(ref);
        img.hidden = true;
        if (empty) {
            empty.hidden = false;
            empty.textContent = I18N.loading || '…';
        }
        img.onload = () => {
            img.hidden = false;
            if (empty) empty.hidden = true;
        };
        img.onerror = () => {
            img.hidden = true;
            if (empty) {
                empty.hidden = false;
                empty.textContent = I18N.preview_failed || '(preview unavailable)';
            }
        };
        img.src = url;
    }

    /** Switch which visual diff mode is shown (side / slider / diff). */
    function setDiffMode(mode) {
        document.querySelectorAll('.diff-mode-btn').forEach((b) => {
            b.classList.toggle('active', b.dataset.mode === mode);
        });
        document.querySelectorAll('[data-mode]').forEach((el) => {
            if (!el.classList.contains('diff-mode-btn')) {
                el.hidden = el.dataset.mode !== mode;
            }
        });
    }

    /** Slider value (0–100) → opacity of the top image in slider mode. */
    function applySliderValue(v) {
        const top = document.querySelector('#diffModeSlider .overlay-stack__top');
        if (top) top.style.opacity = (v / 100).toString();
    }

    async function doRestore(ts) {
        if (!confirm(I18N.confirm_restore || 'Restore this version?')) return;
        try {
            const r = await fetch(
                '/api/templates/' + encodeURIComponent(TEMPLATE) + '/versions/' + ts + '/restore',
                { method: 'POST' });
            const data = await r.json();
            if (!r.ok || !data.ok) {
                showResult(I18N.restore_failed || 'Restore failed', true);
                return;
            }
            showResult(I18N.restored || 'Restored', false);
            setTimeout(() => location.reload(), 800);
        } catch (e) {
            showResult((I18N.restore_failed || 'Restore failed') + ': ' + e, true);
        }
    }

    document.addEventListener('DOMContentLoaded', function () {
        const btn = $('versionsCompareBtn');
        if (btn) btn.addEventListener('click', () => {
            const a = $('versionsCompareA').value;
            const b = $('versionsCompareB').value;
            runCompare(a, b);
        });
        const close = $('versionsDiffClose');
        if (close) close.addEventListener('click', () => {
            $('versionsDiff').hidden = true;
        });
        // Visual diff mode buttons (side / slider / diff)
        document.querySelectorAll('.diff-mode-btn').forEach((b) => {
            b.addEventListener('click', () => setDiffMode(b.dataset.mode));
        });
        // Slider opacity control (slider mode)
        const slider = $('overlaySlider');
        if (slider) slider.addEventListener('input', () => applySliderValue(slider.value));
        loadAll();
    });
})();
