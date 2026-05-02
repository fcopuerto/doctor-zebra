(function () {
    'use strict';

    function showToast(msg, isError) {
        const toast = document.getElementById('toast');
        if (!toast) return;
        toast.textContent = msg;
        toast.classList.toggle('error', !!isError);
        toast.style.display = 'block';
        clearTimeout(showToast._timer);
        showToast._timer = setTimeout(() => {
            toast.style.display = 'none';
        }, 3500);
    }

    function updatePanels(form) {
        const selected = form.querySelector('input[name="backend"]:checked');
        const backend = selected ? selected.value : 'system';
        form.querySelectorAll('.backend-panel').forEach((panel) => {
            const visible = panel.dataset.backend === backend;
            panel.style.display = visible ? 'block' : 'none';
            panel.querySelectorAll('input, select').forEach((el) => {
                el.disabled = !visible;
            });
        });
    }

    async function runRemoteAction(form, action) {
        const resultEl = form.querySelector('.test-result');
        const payload = new FormData(form);
        const endpoint = action === 'print-test'
            ? '/config/print-test'
            : '/config/test';
        if (resultEl) {
            resultEl.textContent = action === 'print-test'
                ? 'Sending test label...'
                : 'Testing connection...';
            resultEl.classList.remove('ok', 'err');
        }
        try {
            const res = await fetch(endpoint, { method: 'POST', body: payload });
            const data = await res.json().catch(() => ({}));
            const ok = res.ok && data.ok;
            const msg = data.message || (ok ? 'OK' : 'Failed');
            showToast(msg, !ok);
            if (resultEl) {
                resultEl.textContent = msg + (data.target ? ' — ' + data.target : '');
                resultEl.classList.add(ok ? 'ok' : 'err');
            }
        } catch (err) {
            showToast('Request failed: ' + err, true);
            if (resultEl) {
                resultEl.textContent = 'Request failed: ' + err;
                resultEl.classList.add('err');
            }
        }
    }

    document.addEventListener('DOMContentLoaded', () => {
        document.querySelectorAll('form.printer-form').forEach((form) => {
            updatePanels(form);
            form.querySelectorAll('input[name="backend"]').forEach((radio) => {
                radio.addEventListener('change', () => updatePanels(form));
            });
            form.querySelectorAll('.btn-test').forEach((btn) => {
                btn.addEventListener('click', () => {
                    runRemoteAction(form, btn.dataset.action || 'test');
                });
            });
        });
    });
})();
