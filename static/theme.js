(function () {
    'use strict';
    function apply(mode) {
        document.documentElement.setAttribute('data-theme', mode);
        try { localStorage.setItem('zebra-theme', mode); } catch (e) { }
    }
    document.addEventListener('DOMContentLoaded', () => {
        const btn = document.getElementById('themeToggle');
        if (!btn) return;
        btn.addEventListener('click', () => {
            const current = document.documentElement.getAttribute('data-theme') || 'light';
            apply(current === 'dark' ? 'light' : 'dark');
        });
    });
})();
