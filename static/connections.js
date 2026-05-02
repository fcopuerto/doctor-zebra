(function () {
    'use strict';

    const form = () => document.getElementById('connectionForm');
    const result = () => document.getElementById('connResult');
    const titleEl = () => document.getElementById('connFormTitle');
    const resetBtn = () => document.getElementById('connReset');

    function showToast(msg, isError) {
        const t = document.getElementById('toast');
        if (!t) return;
        t.textContent = msg;
        t.classList.toggle('error', !!isError);
        t.style.display = 'block';
        clearTimeout(showToast._timer);
        showToast._timer = setTimeout(() => { t.style.display = 'none'; }, 3500);
    }

    function syncAuth() {
        const f = form();
        const auth = f.querySelector('input[name="auth"]:checked').value;
        const block = document.getElementById('conn_sqlauth');
        block.style.display = auth === 'sql' ? '' : 'none';
        block.querySelectorAll('input').forEach((i) => { i.disabled = auth !== 'sql'; });
    }

    function showResult(msg, ok) {
        const r = result();
        r.textContent = msg;
        r.classList.toggle('ok', !!ok);
        r.classList.toggle('err', !ok);
    }

    function clearForm() {
        const f = form();
        f.reset();
        f.querySelector('input[name="connection_name"]').readOnly = false;
        titleEl().textContent = 'Add a connection';
        resetBtn().hidden = true;
        showResult('', true);
        syncAuth();
    }

    function loadIntoForm(data) {
        const f = form();
        f.querySelector('input[name="connection_name"]').value = data.name || '';
        f.querySelector('input[name="connection_name"]').readOnly = true;
        const opt = data.options || {};
        ['server', 'database', 'port', 'driver', 'username', 'encrypt', 'trust_server_certificate']
            .forEach((k) => {
                const el = f.querySelector(`[name="${k}"]`);
                if (el && opt[k] !== undefined) el.value = opt[k] || '';
            });
        const auth = (opt.auth || 'sql').toLowerCase();
        const radio = f.querySelector(`input[name="auth"][value="${auth}"]`);
        if (radio) radio.checked = true;
        f.querySelector('input[name="password"]').value = '';
        titleEl().textContent = `Edit "${data.name}"`;
        resetBtn().hidden = false;
        syncAuth();
        f.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    async function callAction(url, formData) {
        const res = await fetch(url, { method: 'POST', body: formData });
        return { status: res.status, data: await res.json().catch(() => ({})) };
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

    async function onSubmit(e) {
        e.preventDefault();
        const submit = form().querySelector('button[type="submit"]');
        await withBusy(submit, async () => {
            const fd = new FormData(form());
            const { status, data } = await callAction('/config/connections', fd);
            if (status === 200 && data.ok) {
                showToast(data.message);
                window.location.reload();
            } else {
                showToast(data.message || 'Save failed', true);
            }
        });
    }

    async function onTest() {
        showResult('Testing connection…', true);
        await withBusy(document.getElementById('connTest'), async () => {
            const fd = new FormData(form());
            const { data } = await callAction('/config/connections/test', fd);
            showResult(data.message || (data.ok ? 'OK' : 'Failed'), data.ok);
            showToast(data.message || (data.ok ? 'OK' : 'Failed'), !data.ok);
        });
    }

    async function onDelete(name) {
        if (!confirm(`Delete connection "${name}"?`)) return;
        const { data } = await callAction(`/config/connections/${encodeURIComponent(name)}/delete`, new FormData());
        if (data.ok) {
            showToast(data.message || 'Deleted');
            window.location.reload();
        } else {
            showToast(data.message || 'Delete failed', true);
        }
    }

    function bindRows() {
        document.querySelectorAll('#connectionsBody [data-action="edit-conn"]').forEach((b) => {
            b.addEventListener('click', () => {
                const tr = b.closest('tr');
                const data = JSON.parse(tr.dataset.conn);
                loadIntoForm(data);
            });
        });
        document.querySelectorAll('#connectionsBody [data-action="delete-conn"]').forEach((b) => {
            b.addEventListener('click', () => onDelete(b.dataset.name));
        });
    }

    document.addEventListener('DOMContentLoaded', () => {
        const f = form();
        if (!f) return;
        f.addEventListener('submit', onSubmit);
        f.querySelectorAll('input[name="auth"]').forEach((r) => r.addEventListener('change', syncAuth));
        document.getElementById('connTest').addEventListener('click', onTest);
        resetBtn().addEventListener('click', clearForm);
        bindRows();
        syncAuth();
    });
})();
