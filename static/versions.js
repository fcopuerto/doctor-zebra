/* Template version history dialog.
 *
 * Lists snapshots (newest first) with their version number, lets you:
 *   - Click "View" to preview the saved ZPL inline.
 *   - Tick two versions and click "Compare" → unified diff inline.
 *   - Restore a chosen version (snapshots the live one first, so the
 *     restore is itself reversible).
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

    async function openDialog() {
        const dlg = $('versionsDialog');
        if (!dlg) return;
        $('versionsDetail').hidden = true;
        $('versionsList').hidden = false;
        $('versionsDiff').hidden = true;
        $('versionsList').innerHTML = '<p class="muted">…</p>';
        if (typeof dlg.showModal === 'function') dlg.showModal();
        else dlg.setAttribute('open', '');
        await loadList();
    }

    function closeDialog() {
        const dlg = $('versionsDialog');
        if (!dlg) return;
        if (typeof dlg.close === 'function') dlg.close();
        else dlg.removeAttribute('open');
    }

    async function loadList() {
        try {
            const r = await fetch('/api/templates/' + encodeURIComponent(TEMPLATE) + '/versions');
            const data = await r.json();
            renderList(data.versions || []);
        } catch (e) {
            $('versionsList').innerHTML = '<p class="muted">Error: ' + e + '</p>';
        }
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

        // "Compare current" pseudo-row at the top — lets the user pick
        // any saved version and diff it against the live file.
        const tools = document.createElement('div');
        tools.className = 'versions-tools';
        tools.innerHTML = `
            <span class="muted">${I18N.compare_hint || 'Tick up to two versions to compare'}</span>
            <button type="button" id="versionsCompareBtn" disabled>${I18N.compare || 'Compare'}</button>
            <button type="button" class="btn-ghost" id="versionsCompareCurrentBtn" disabled>
                ${I18N.compare_with_current || 'Compare with current'}
            </button>`;
        list.appendChild(tools);

        versions.forEach((v) => {
            const row = document.createElement('div');
            row.className = 'version-row';
            row.dataset.ts = v.timestamp;
            row.innerHTML = `
                <input type="checkbox" class="version-row__pick" aria-label="select for compare">
                <div class="version-row__main">
                    <strong></strong>
                    <span class="muted"></span>
                </div>
                <button type="button" class="btn-ghost" data-action="view"></button>`;
            row.querySelector('strong').textContent =
                'v' + v.version + ' · ' + (v.ts_human || v.timestamp);
            const meta = (v.size_bytes || 0) + ' B' +
                (v.has_sidecar ? ' · ' + (I18N.has_sidecar || 'with sidecar') : ' · ' + (I18N.no_sidecar || 'no sidecar')) +
                (v.reason ? ' · ' + v.reason : '');
            row.querySelector('.muted').textContent = meta;
            const viewBtn = row.querySelector('[data-action="view"]');
            viewBtn.textContent = I18N.view || 'View';
            viewBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                loadDetail(v.timestamp, 'v' + v.version + ' · ' + v.ts_human);
            });
            row.querySelector('input').addEventListener('change', updateCompareControls);
            list.appendChild(row);
        });

        document.getElementById('versionsCompareBtn').addEventListener('click', compareSelected);
        document.getElementById('versionsCompareCurrentBtn').addEventListener('click', compareWithCurrent);
    }

    function selectedRows() {
        return Array.from(document.querySelectorAll('.version-row__pick:checked'))
            .map((c) => c.closest('.version-row').dataset.ts);
    }

    function updateCompareControls() {
        const picks = selectedRows();
        document.getElementById('versionsCompareBtn').disabled = picks.length !== 2;
        document.getElementById('versionsCompareCurrentBtn').disabled = picks.length !== 1;
        // Cap selection at 2: uncheck the oldest selection if user picks a third.
        if (picks.length > 2) {
            const checks = Array.from(document.querySelectorAll('.version-row__pick:checked'));
            checks[0].checked = false;
            updateCompareControls();
        }
    }

    async function compareSelected() {
        const picks = selectedRows();
        if (picks.length !== 2) return;
        await runCompare(picks[0], picks[1]);
    }

    async function compareWithCurrent() {
        const picks = selectedRows();
        if (picks.length !== 1) return;
        await runCompare(picks[0], 'current');
    }

    async function runCompare(a, b) {
        try {
            const r = await fetch(
                '/api/templates/' + encodeURIComponent(TEMPLATE) +
                '/versions/compare?a=' + encodeURIComponent(a) + '&b=' + encodeURIComponent(b));
            const data = await r.json();
            renderDiff(data);
        } catch (e) {
            showResult('Error: ' + e, true);
        }
    }

    function renderDiff(d) {
        $('versionsList').hidden = true;
        $('versionsDetail').hidden = true;
        const box = $('versionsDiff');
        box.hidden = false;
        $('versionsDiffTitle').textContent =
            (d.a_label || '?') + '  →  ' + (d.b_label || '?');
        const out = $('versionsDiffBody');
        out.innerHTML = '';
        const lines = d.lines || [];
        if (!lines.length) {
            const p = document.createElement('p');
            p.className = 'muted';
            p.textContent = I18N.no_diff || 'No differences.';
            out.appendChild(p);
            return;
        }
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

    let currentTs = null;

    async function loadDetail(ts, label) {
        currentTs = ts;
        try {
            const r = await fetch(
                '/api/templates/' + encodeURIComponent(TEMPLATE) + '/versions/' + ts);
            const data = await r.json();
            $('versionsDetailTitle').textContent = label || ts;
            $('versionsDetailZpl').textContent = data.zpl || '';
            $('versionsList').hidden = true;
            $('versionsDiff').hidden = true;
            $('versionsDetail').hidden = false;
            showResult('', false);
        } catch (e) {
            showResult('Error: ' + e, true);
        }
    }

    async function restoreCurrent() {
        if (!currentTs) return;
        if (!confirm(I18N.confirm_restore || 'Restore this version?')) return;
        try {
            const r = await fetch(
                '/api/templates/' + encodeURIComponent(TEMPLATE) + '/versions/' + currentTs + '/restore',
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

    function backToList() {
        $('versionsDetail').hidden = true;
        $('versionsDiff').hidden = true;
        $('versionsList').hidden = false;
    }

    document.addEventListener('DOMContentLoaded', function () {
        const open = $('versionsButton');
        if (open) open.addEventListener('click', openDialog);
        const close = $('versionsClose');
        if (close) close.addEventListener('click', closeDialog);
        const back = $('versionsBack');
        if (back) back.addEventListener('click', backToList);
        const backDiff = $('versionsDiffBack');
        if (backDiff) backDiff.addEventListener('click', backToList);
        const restore = $('versionsRestore');
        if (restore) restore.addEventListener('click', restoreCurrent);
    });
})();
