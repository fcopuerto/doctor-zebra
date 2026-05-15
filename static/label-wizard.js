/* Label wizard — live preview.
 *
 * Posts the wizard form to /api/wizard/preview (which bakes the ZPL and
 * renders it via Labelary) and shows the PNG. Debounced + deduped like
 * the print form's auto-preview so we don't hammer Labelary on every
 * keystroke. The form's normal submit still POSTs to /templates/wizard
 * and saves — JS only drives the preview.
 *
 * Distinct from static/wizard.js (the first-run setup wizard); different
 * file + form id (#labelWizardForm) so the two never interfere.
 */
(function () {
    'use strict';

    const form = document.getElementById('labelWizardForm');
    const frame = document.getElementById('wizPreviewFrame');
    if (!form || !frame) return;

    let lastKey = '';
    let timer = null;
    let inFlight = false;
    let objUrl = null;

    function formKey(fd) {
        const e = [];
        fd.forEach((v, k) => e.push(k + '=' + v));
        return e.sort().join('&');
    }

    async function render() {
        const fd = new FormData(form);
        const key = formKey(fd);
        if (key === lastKey || inFlight) return;
        lastKey = key;
        inFlight = true;
        try {
            const res = await fetch('/api/wizard/preview', { method: 'POST', body: fd });
            if (!res.ok) {
                frame.innerHTML = '<p class="muted">Preview unavailable (offline?). '
                    + 'The label will still print fine.</p>';
                return;
            }
            const blob = await res.blob();
            const url = URL.createObjectURL(blob);
            const img = new Image();
            img.alt = 'Label preview';
            img.className = 'label-preview-img';
            img.onload = () => {
                frame.innerHTML = '';
                frame.appendChild(img);
                if (objUrl) URL.revokeObjectURL(objUrl);
                objUrl = url;
            };
            img.src = url;
        } catch (e) {
            /* offline — silent, manual refresh still works */
        } finally {
            inFlight = false;
        }
    }

    function schedule(immediate) {
        clearTimeout(timer);
        timer = setTimeout(render, immediate ? 0 : 600);
    }

    form.addEventListener('input', () => schedule());
    form.addEventListener('change', () => schedule());

    const magRange = document.getElementById('magRange');
    const magOut = document.getElementById('magOut');
    if (magRange && magOut) {
        magRange.addEventListener('input', () => { magOut.textContent = magRange.value; });
    }

    const refresh = document.getElementById('wizRefresh');
    if (refresh) refresh.addEventListener('click', () => { lastKey = ''; schedule(true); });

    // First paint once the page settles.
    setTimeout(() => schedule(true), 400);
})();
