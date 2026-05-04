/* Settings → Tools: fire one-shot ZPL utilities at the printer. */
(function () {
    'use strict';

    const I18N = window.TOOLS_I18N || {};

    function showResult(msg, isError) {
        const el = document.getElementById('toolResult');
        if (!el) return;
        el.textContent = msg;
        el.className = 'test-result' + (isError ? ' error' : ' ok');
    }

    async function runTool(toolId, btn) {
        if (btn.dataset.confirm === '1') {
            const ok = window.confirm(I18N.confirm || 'Are you sure?');
            if (!ok) return;
        }
        const original = btn.disabled;
        btn.disabled = true;
        showResult(I18N.sending || 'Sending…', false);
        try {
            const r = await fetch('/api/tools/run', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ tool_id: toolId }),
            });
            const data = await r.json();
            if (!r.ok || !data.ok) {
                showResult((I18N.error || 'Error') + ': ' + (data.message || r.status), true);
            } else {
                showResult(data.message || 'OK', false);
            }
        } catch (e) {
            showResult((I18N.error || 'Error') + ': ' + e, true);
        } finally {
            btn.disabled = original;
        }
    }

    document.addEventListener('DOMContentLoaded', function () {
        document.querySelectorAll('.tool-card[data-tool]').forEach((btn) => {
            btn.addEventListener('click', () => runTool(btn.dataset.tool, btn));
        });
    });
})();
