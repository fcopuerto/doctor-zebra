(function () {
    'use strict';
    function apply(mode) {
        document.documentElement.setAttribute('data-theme', mode);
        try { localStorage.setItem('zebra-theme', mode); } catch (e) { }
    }
    document.addEventListener('DOMContentLoaded', () => {
        const btn = document.getElementById('themeToggle');
        if (btn) {
            btn.addEventListener('click', () => {
                const current = document.documentElement.getAttribute('data-theme') || 'light';
                apply(current === 'dark' ? 'light' : 'dark');
            });
        }

        // Language switcher: POST to /api/lang/<code>, then reload so the
        // server re-renders the page with the chosen catalog.
        document.querySelectorAll('.lang-switcher__btn').forEach(b => {
            b.addEventListener('click', async () => {
                const code = b.getAttribute('data-lang');
                if (!code || b.classList.contains('active')) return;
                try {
                    const r = await fetch(`/api/lang/${encodeURIComponent(code)}`, {
                        method: 'POST',
                        headers: { 'Accept': 'application/json' },
                    });
                    if (r.ok) location.reload();
                } catch (e) {
                    console.error('Failed to switch language', e);
                }
            });
        });
    });
})();
