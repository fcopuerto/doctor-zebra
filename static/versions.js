/* Template version history dialog.
 *
 * The Versions button in the breadcrumb of the Edit Template page opens
 * a modal that lists every snapshot, lets the user preview the saved
 * ZPL, and offers a Restore button (with confirm) that asks the
 * server to swap the live file with the chosen snapshot. The server
 * always snapshots the current file before restoring, so undo works.
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
        versions.forEach((v) => {
            const row = document.createElement('div');
            row.className = 'version-row';
            row.innerHTML = `
                <div class="version-row__main">
                    <strong></strong>
                    <span class="muted"></span>
                </div>
                <button type="button" class="btn-ghost"></button>`;
            row.querySelector('strong').textContent = v.ts_human || v.timestamp;
            const meta = (v.size_bytes || 0) + ' B' +
                (v.has_sidecar ? ' · ' + (I18N.has_sidecar || 'with sidecar') : ' · ' + (I18N.no_sidecar || 'no sidecar')) +
                (v.reason ? ' · ' + v.reason : '');
            row.querySelector('.muted').textContent = meta;
            const btn = row.querySelector('button');
            btn.textContent = I18N.view || 'View';
            btn.addEventListener('click', () => loadDetail(v.timestamp, v.ts_human));
            list.appendChild(row);
        });
    }

    let currentTs = null;

    async function loadDetail(ts, human) {
        currentTs = ts;
        try {
            const r = await fetch(
                '/api/templates/' + encodeURIComponent(TEMPLATE) + '/versions/' + ts);
            const data = await r.json();
            $('versionsDetailTitle').textContent = human || ts;
            $('versionsDetailZpl').textContent = data.zpl || '';
            $('versionsList').hidden = true;
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
            // Reload the page after a beat so the editor reflects the new state.
            setTimeout(() => location.reload(), 800);
        } catch (e) {
            showResult((I18N.restore_failed || 'Restore failed') + ': ' + e, true);
        }
    }

    document.addEventListener('DOMContentLoaded', function () {
        const open = $('versionsButton');
        if (open) open.addEventListener('click', openDialog);
        const close = $('versionsClose');
        if (close) close.addEventListener('click', closeDialog);
        const back = $('versionsBack');
        if (back) back.addEventListener('click', function () {
            $('versionsDetail').hidden = true;
            $('versionsList').hidden = false;
        });
        const restore = $('versionsRestore');
        if (restore) restore.addEventListener('click', restoreCurrent);
    });
})();
