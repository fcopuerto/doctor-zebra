(function () {
    'use strict';

    const TOTAL_STEPS = 5;

    function showToast(msg, isError) {
        const toast = document.getElementById('toast');
        if (!toast) return;
        toast.textContent = msg;
        toast.classList.toggle('error', !!isError);
        toast.style.display = 'block';
        clearTimeout(showToast._timer);
        showToast._timer = setTimeout(() => { toast.style.display = 'none'; }, 3500);
    }

    function selectedBackend(form) {
        const r = form.querySelector('input[name="backend"]:checked');
        return r ? r.value : 'system';
    }

    function targetSummary(form) {
        const backend = selectedBackend(form);
        if (backend === 'tcp') {
            const host = (form.querySelector('input[name="tcp_host"]').value || '').trim();
            const port = (form.querySelector('input[name="tcp_port"]').value || '9100').trim();
            if (!host) return '';
            return port === '9100' ? host : `${host}:${port}`;
        }
        if (backend === 'system') {
            const name = (form.querySelector('select[name="system_printer"]').value || '').trim();
            if (!name) return '';
            return (window.__IS_WINDOWS__ ? 'win://' : 'cups://') + name;
        }
        if (backend === 'advanced') {
            return (form.querySelector('input[name="raw_target"]').value || '').trim();
        }
        return '';
    }

    function backendLabel(backend) {
        return ({
            system: 'System printer',
            tcp: 'Network (TCP 9100)',
            advanced: 'Advanced',
        })[backend] || backend;
    }

    function updatePanels(form) {
        const backend = selectedBackend(form);
        form.querySelectorAll('.backend-panel').forEach((panel) => {
            const visible = panel.dataset.backend === backend;
            panel.style.display = visible ? 'block' : 'none';
            panel.querySelectorAll('input, select').forEach((el) => {
                el.disabled = !visible;
            });
        });
    }

    function validateStep(form, step) {
        if (step === 3) {
            const backend = selectedBackend(form);
            if (backend === 'system') {
                const name = form.querySelector('select[name="system_printer"]').value;
                if (!name) {
                    showToast('Please pick a printer first.', true);
                    return false;
                }
            } else if (backend === 'tcp') {
                const host = form.querySelector('input[name="tcp_host"]').value.trim();
                if (!host) {
                    showToast('Enter the printer IP or hostname.', true);
                    return false;
                }
            } else if (backend === 'advanced') {
                const raw = form.querySelector('input[name="raw_target"]').value.trim();
                if (!raw) {
                    showToast('Enter a raw target string.', true);
                    return false;
                }
            }
        }
        return true;
    }

    function renderReview(form) {
        const backend = selectedBackend(form);
        form.querySelector('[data-review="backend"]').textContent = backendLabel(backend);
        form.querySelector('[data-review="target"]').textContent = targetSummary(form) || '(empty)';
        form.querySelector('[data-review="templates_dir"]').textContent =
            form.querySelector('input[name="templates_dir"]').value || 'templates_zpl';
    }

    function setStep(form, step) {
        step = Math.max(1, Math.min(TOTAL_STEPS, step));
        form.dataset.step = String(step);

        form.querySelectorAll('.wizard-step').forEach((section) => {
            const n = Number(section.dataset.step);
            section.hidden = n !== step;
        });

        document.querySelectorAll('.wizard-steps li').forEach((li) => {
            const n = Number(li.dataset.step);
            li.classList.toggle('active', n === step);
            li.classList.toggle('done', n < step);
        });

        const back = form.querySelector('[data-nav="back"]');
        const next = form.querySelector('[data-nav="next"]');
        const save = form.querySelector('[data-nav="save"]');
        back.disabled = step === 1;
        if (step === TOTAL_STEPS) {
            next.hidden = true;
            save.hidden = false;
            renderReview(form);
        } else {
            next.hidden = false;
            save.hidden = true;
        }
    }

    async function runRemoteAction(form, action) {
        const resultEl = form.querySelector('.test-result');
        const payload = new FormData(form);
        const endpoint = action === 'print-test' ? '/config/print-test' : '/config/test';
        if (resultEl) {
            resultEl.textContent = action === 'print-test'
                ? 'Sending test label...' : 'Testing connection...';
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
        }
    }

    document.addEventListener('DOMContentLoaded', () => {
        const form = document.getElementById('wizardForm');
        if (!form) return;

        updatePanels(form);
        setStep(form, 1);

        form.querySelectorAll('input[name="backend"]').forEach((radio) => {
            radio.addEventListener('change', () => updatePanels(form));
        });
        form.querySelectorAll('.btn-test').forEach((btn) => {
            btn.addEventListener('click', () => runRemoteAction(form, btn.dataset.action || 'test'));
        });

        form.querySelector('[data-nav="back"]').addEventListener('click', () => {
            const current = Number(form.dataset.step || '1');
            setStep(form, current - 1);
        });
        form.querySelector('[data-nav="next"]').addEventListener('click', () => {
            const current = Number(form.dataset.step || '1');
            if (!validateStep(form, current)) return;
            setStep(form, current + 1);
        });
    });
})();
