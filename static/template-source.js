(function () {
    'use strict';

    const $ = (id) => document.getElementById(id);
    const editor = () => document.querySelector('.source-editor');
    const ta = () => $('srcTextarea');
    const previewFrame = () => $('srcPreviewFrame');
    const status = () => $('srcStatus');
    const meta = () => $('srcMeta');

    function showToast(msg, isError) {
        const t = document.getElementById('toast');
        if (!t) return;
        t.textContent = msg;
        t.classList.toggle('error', !!isError);
        t.style.display = 'block';
        clearTimeout(showToast._timer);
        showToast._timer = setTimeout(() => { t.style.display = 'none'; }, 3000);
    }

    async function withBusy(btn, fn) {
        if (!btn) return await fn();
        const wasDisabled = btn.disabled;
        btn.disabled = true;
        btn.classList.add('is-busy');
        try { return await fn(); }
        finally { btn.disabled = wasDisabled; btn.classList.remove('is-busy'); }
    }

    let _initial = '';
    let _saved = '';
    let _previewTimer = null;
    let _saveOnNextDirty = true;

    function dirty() { return ta().value !== _saved; }

    function updateStatus() {
        if (dirty()) {
            status().textContent = 'Unsaved changes';
            status().className = 'src-status src-status--dirty';
        } else {
            status().textContent = 'Saved';
            status().className = 'src-status src-status--clean';
        }
        const text = ta().value;
        const lines = text.split('\n').length;
        const bytes = new Blob([text]).size;
        meta().textContent = `${lines} line${lines === 1 ? '' : 's'} · ${bytes.toLocaleString()} bytes`;
    }

    async function refreshPreview() {
        const zpl = ta().value;
        if (!zpl.trim()) {
            previewFrame().innerHTML = '<p class="muted">Empty source — nothing to render.</p>';
            return;
        }
        previewFrame().innerHTML = '<p class="muted">Rendering…</p>';
        try {
            const res = await fetch('/api/preview/raw', {
                method: 'POST',
                headers: { 'Content-Type': 'text/plain; charset=utf-8' },
                body: zpl,
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) {
                previewFrame().innerHTML =
                    `<p class="src-error">${data.error || 'Preview failed'}</p>`;
                return;
            }
            previewFrame().innerHTML =
                `<img src="${data.image_url}" alt="Label preview" class="label-preview-img">`;
        } catch (err) {
            previewFrame().innerHTML =
                `<p class="src-error">Preview failed: ${err.message || err}</p>`;
        }
    }

    function scheduleAutoPreview() {
        clearTimeout(_previewTimer);
        _previewTimer = setTimeout(() => { refreshPreview(); }, 600);
    }

    async function save() {
        const file = editor().dataset.templateFile;
        const zpl = ta().value;
        await withBusy($('srcSave'), async () => {
            try {
                const fd = new FormData();
                fd.append('zpl', zpl);
                const res = await fetch(
                    '/templates/' + encodeURIComponent(file) + '/source',
                    { method: 'POST', body: fd },
                );
                const data = await res.json().catch(() => ({}));
                if (!res.ok || !data.ok) {
                    showToast(data.error || 'Save failed', true);
                    return;
                }
                _saved = zpl;
                showToast(`Saved ${file} (${data.bytes} bytes)`);
                updateStatus();
            } catch (err) {
                showToast('Save failed: ' + err, true);
            }
        });
    }

    function revert() {
        if (!dirty()) { showToast('Nothing to revert.'); return; }
        if (!confirm('Discard unsaved changes and reload the saved version?')) return;
        ta().value = _saved;
        updateStatus();
        scheduleAutoPreview();
    }

    document.addEventListener('DOMContentLoaded', () => {
        if (!editor()) return;
        _initial = ta().value;
        _saved = _initial;
        updateStatus();
        refreshPreview();

        ta().addEventListener('input', () => {
            updateStatus();
            scheduleAutoPreview();
        });

        // Tab key inserts spaces instead of changing focus
        ta().addEventListener('keydown', (e) => {
            if (e.key === 'Tab') {
                e.preventDefault();
                const start = ta().selectionStart;
                const end = ta().selectionEnd;
                const before = ta().value.substring(0, start);
                const after = ta().value.substring(end);
                ta().value = before + '    ' + after;
                ta().selectionStart = ta().selectionEnd = start + 4;
                updateStatus();
                scheduleAutoPreview();
            }
        });

        $('srcSave').addEventListener('click', save);
        $('srcRevert').addEventListener('click', revert);
        $('srcRefresh').addEventListener('click', refreshPreview);

        // Cmd/Ctrl + S → Save
        document.addEventListener('keydown', (e) => {
            if ((e.metaKey || e.ctrlKey) && (e.key === 's' || e.key === 'S')) {
                e.preventDefault();
                save();
            }
        });

        // Beforeunload guard
        window.addEventListener('beforeunload', (e) => {
            if (!dirty()) return;
            e.preventDefault();
            e.returnValue = '';
        });
    });
})();
