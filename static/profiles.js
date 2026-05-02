(function () {
    'use strict';

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
        try { return await fn(); }
        finally { btn.disabled = wasDisabled; btn.classList.remove('is-busy'); }
    }

    async function postForm(url, fields) {
        const fd = new FormData();
        for (const [k, v] of Object.entries(fields)) fd.append(k, v);
        const res = await fetch(url, { method: 'POST', body: fd });
        const data = await res.json().catch(() => ({}));
        return { ok: res.ok && data.ok, data, status: res.status };
    }

    function showRestartBanner(message) {
        const banner = document.getElementById('restartBanner');
        const msg = document.getElementById('restartMessage');
        if (msg && message) msg.textContent = message;
        if (banner) banner.hidden = false;
    }

    async function onSwitch(btn) {
        const name = btn.dataset.name;
        if (!confirm(`Switch active profile to "${name}"?\n\nThe app must be restarted for the change to take effect.`)) return;
        await withBusy(btn, async () => {
            const { ok, data } = await postForm('/config/profiles/switch', { name });
            if (!ok) { showToast(data.message || 'Switch failed', true); return; }
            showToast(data.message);
            if (data.restart_required) showRestartBanner(data.message);
        });
    }

    async function onDelete(btn) {
        const name = btn.dataset.name;
        if (!confirm(`Delete profile "${name}"?\n\nThis permanently removes its templates, connections, label history and printer config. Cannot be undone.`)) return;
        await withBusy(btn, async () => {
            const { ok, data } = await postForm('/config/profiles/delete', { name });
            if (!ok) { showToast(data.message || 'Delete failed', true); return; }
            showToast(data.message);
            const row = btn.closest('tr');
            if (row) row.remove();
        });
    }

    async function onCreate(e) {
        e.preventDefault();
        const form = document.getElementById('newProfileForm');
        const result = document.getElementById('newProfileResult');
        const submit = form.querySelector('button[type="submit"]');
        await withBusy(submit, async () => {
            const fd = new FormData(form);
            const { ok, data } = await postForm('/config/profiles/create',
                { name: fd.get('name') });
            if (!ok) {
                result.textContent = data.message || 'Create failed';
                result.classList.add('err'); result.classList.remove('ok');
                return;
            }
            result.textContent = data.message;
            result.classList.add('ok'); result.classList.remove('err');
            showToast(data.message);
            // Reload to show the new row
            setTimeout(() => window.location.reload(), 600);
        });
    }

    document.addEventListener('DOMContentLoaded', () => {
        const body = document.getElementById('profilesBody');
        if (!body) return;
        body.querySelectorAll('[data-action="switch"]').forEach((b) => {
            b.addEventListener('click', () => onSwitch(b));
        });
        body.querySelectorAll('[data-action="delete"]').forEach((b) => {
            b.addEventListener('click', () => onDelete(b));
        });
        const form = document.getElementById('newProfileForm');
        if (form) form.addEventListener('submit', onCreate);
        const dismiss = document.getElementById('restartDismiss');
        if (dismiss) dismiss.addEventListener('click', () => {
            document.getElementById('restartBanner').hidden = true;
        });
    });
})();
