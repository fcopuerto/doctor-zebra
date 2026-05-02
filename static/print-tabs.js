/* Print tabs.
 *
 * Lets the user have several in-flight print jobs open in parallel: each
 * tab keeps its own template + field values + copies, all in
 * sessionStorage, all client-side. The server still sees a single form on
 * submit; tabs are just a UX layer over the existing /print page.
 *
 * Coordination with app.js: when the active template changes, app.js
 * fetches the spec from /api/fields/<template> and re-renders the inputs.
 * After it's done it dispatches a `fields:rendered` event on
 * #fieldsContainer, which is when we restore the saved values for the
 * incoming tab.
 */
(function () {
    'use strict';

    const STORAGE_KEY = 'cz_print_tabs_v1';
    const ACTIVE_KEY  = 'cz_print_active_tab_v1';
    // Hard cap so a runaway loop can't fill sessionStorage with thousands
    // of tabs. The UI stops offering "+" past this.
    const MAX_TABS = 12;

    // ------------------------------------------------------------------ DOM
    const tplSelect  = () => document.getElementById('template_file');
    const fieldsCont = () => document.getElementById('fieldsContainer');
    const copiesIn   = () => document.getElementById('copies');

    // ------------------------------------------------------------------ State
    function loadState() {
        try {
            const tabs = JSON.parse(sessionStorage.getItem(STORAGE_KEY) || '[]');
            return Array.isArray(tabs) ? tabs : [];
        } catch (e) { return []; }
    }
    function saveState(tabs) {
        try { sessionStorage.setItem(STORAGE_KEY, JSON.stringify(tabs)); } catch (e) {}
    }
    function loadActive() {
        return sessionStorage.getItem(ACTIVE_KEY) || '';
    }
    function saveActive(id) {
        try { sessionStorage.setItem(ACTIVE_KEY, id); } catch (e) {}
    }

    function makeId() {
        return 't' + Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
    }

    function newTab(template) {
        return {
            id: makeId(),
            template: template || (tplSelect() && tplSelect().value) || '',
            values: {},
            copies: 1,
        };
    }

    // ------------------------------------------------------------------ Capture/apply

    /** Read the form into the given tab object (mutates in place). */
    function captureInto(tab) {
        if (!tab) return;
        const tpl = tplSelect();
        if (tpl) tab.template = tpl.value || tab.template;
        const c = copiesIn();
        if (c) tab.copies = Math.max(1, parseInt(c.value, 10) || 1);
        const vals = {};
        const fc = fieldsCont();
        if (fc) {
            fc.querySelectorAll('[data-field-key]').forEach((row) => {
                const key = row.dataset.fieldKey;
                const inp = row.querySelector('input,textarea,select');
                if (key && inp) vals[key] = inp.value;
            });
        }
        tab.values = vals;
        tab.overrides = readOverrides();
    }

    /** Restore the given tab's values into the currently rendered fields. */
    function applyValuesNow(tab) {
        const fc = fieldsCont();
        if (!fc || !tab) return;
        Object.entries(tab.values || {}).forEach(([key, val]) => {
            const row = fc.querySelector(`[data-field-key="${CSS.escape(key)}"]`);
            const inp = row && row.querySelector('input,textarea,select');
            if (inp) {
                inp.value = val;
                inp.dispatchEvent(new Event('change', { bubbles: true }));
            }
        });
        const c = copiesIn();
        if (c && tab.copies) c.value = tab.copies;
        if (tab.overrides) applyOverrides(tab.overrides);
    }

    /** Snapshot the per-job print overrides currently in the form. */
    function readOverrides() {
        const out = {};
        const mt = document.querySelector('input[name="media_type"]:checked');
        if (mt) out.media_type = mt.value;
        const sp = document.getElementById('job_speed');
        if (sp) out.speed_ips = sp.value;
        const dk = document.getElementById('job_darkness');
        if (dk) out.darkness = dk.value;
        return out;
    }

    /** Push a saved override snapshot back into the form controls. */
    function applyOverrides(ov) {
        const mt = (ov.media_type || '');
        document.querySelectorAll('input[name="media_type"]').forEach((r) => {
            r.checked = r.value === mt;
        });
        const sp = document.getElementById('job_speed');
        if (sp && ov.speed_ips !== undefined) sp.value = ov.speed_ips;
        const dk = document.getElementById('job_darkness');
        if (dk && ov.darkness !== undefined) {
            dk.value = ov.darkness;
            const lbl = document.getElementById('job_darkness_value');
            if (lbl) lbl.textContent = dk.value < 0 ? '—' : dk.value;
        }
    }

    /**
     * Activate ``id``: switch the template select if needed (which causes
     * app.js to refetch fields), and queue value restoration for as soon
     * as the new fields land.
     */
    function activate(id) {
        const tabs = loadState();
        const tab  = tabs.find((t) => t.id === id);
        if (!tab) return;
        saveActive(id);
        renderBar();

        const tpl = tplSelect();
        const needsReload = tpl && tab.template && tpl.value !== tab.template;

        if (needsReload) {
            // Listen once for the rebuild event, then restore.
            const fc = fieldsCont();
            const onceRendered = () => {
                fc.removeEventListener('fields:rendered', onceRendered);
                applyValuesNow(tab);
            };
            fc.addEventListener('fields:rendered', onceRendered);
            tpl.value = tab.template;
            tpl.dispatchEvent(new Event('change', { bubbles: true }));
        } else {
            // Same template — just paint the values in.
            applyValuesNow(tab);
        }
    }

    function addTab() {
        const tabs = loadState();
        if (tabs.length >= MAX_TABS) return;
        // Snapshot whichever tab is active before mutating.
        const cur = tabs.find((t) => t.id === loadActive());
        if (cur) captureInto(cur);
        const fresh = newTab();
        tabs.push(fresh);
        saveState(tabs);
        activate(fresh.id);
    }

    function closeTab(id) {
        let tabs = loadState();
        if (tabs.length <= 1) return; // never go below one
        const idx = tabs.findIndex((t) => t.id === id);
        if (idx < 0) return;
        const wasActive = loadActive() === id;
        tabs.splice(idx, 1);
        saveState(tabs);
        if (wasActive) {
            const next = tabs[Math.max(0, idx - 1)];
            activate(next.id);
        } else {
            renderBar();
        }
    }

    // ------------------------------------------------------------------ Render

    function tabLabel(tab) {
        if (!tab.template) return '—';
        // Drop common .zpl suffix and trim long names for the tab.
        const name = tab.template.replace(/\.zpl$/i, '');
        return name.length > 22 ? name.slice(0, 21) + '…' : name;
    }

    function renderBar() {
        const bar = document.getElementById('printTabs');
        if (!bar) return;
        const tabs = loadState();
        const activeId = loadActive();
        bar.innerHTML = '';

        tabs.forEach((tab) => {
            const el = document.createElement('div');
            el.className = 'print-tab' + (tab.id === activeId ? ' active' : '');
            el.dataset.tabId = tab.id;
            el.title = tab.template || '';

            const label = document.createElement('button');
            label.type = 'button';
            label.className = 'print-tab__label';
            label.textContent = tabLabel(tab);
            label.addEventListener('click', () => {
                if (tab.id === loadActive()) return;
                // Snapshot whichever tab the user is leaving.
                const all = loadState();
                const leaving = all.find((t) => t.id === loadActive());
                if (leaving) {
                    captureInto(leaving);
                    saveState(all);
                }
                activate(tab.id);
            });
            el.appendChild(label);

            if (tabs.length > 1) {
                const close = document.createElement('button');
                close.type = 'button';
                close.className = 'print-tab__close';
                close.setAttribute('aria-label', 'Close');
                close.textContent = '×';
                close.addEventListener('click', (e) => {
                    e.stopPropagation();
                    closeTab(tab.id);
                });
                el.appendChild(close);
            }

            bar.appendChild(el);
        });

        const add = document.createElement('button');
        add.type = 'button';
        add.className = 'print-tab__add';
        add.title = 'New tab';
        add.textContent = '+';
        add.disabled = tabs.length >= MAX_TABS;
        add.addEventListener('click', addTab);
        bar.appendChild(add);
    }

    // ------------------------------------------------------------------ Boot

    function bootstrap() {
        if (!document.getElementById('printTabs')) return;

        let tabs = loadState();
        let activeId = loadActive();

        // First visit: seed one tab from whatever the form is currently
        // showing (templates rendered server-side).
        if (tabs.length === 0) {
            const seed = newTab();
            // Capture current form values too, so the very first tab keeps
            // anything pre-filled by the server.
            captureInto(seed);
            tabs = [seed];
            activeId = seed.id;
            saveState(tabs);
            saveActive(activeId);
        } else if (!tabs.find((t) => t.id === activeId)) {
            activeId = tabs[0].id;
            saveActive(activeId);
        }

        renderBar();

        // If the persisted active tab has a different template than what
        // the server rendered, swap it in now. Otherwise just restore the
        // values into the already-rendered form.
        const active = tabs.find((t) => t.id === activeId);
        if (active && active.template &&
            tplSelect() && tplSelect().value !== active.template) {
            activate(activeId);
        } else if (active) {
            applyValuesNow(active);
        }

        // Persist edits as the user types so a refresh / new tab keeps state.
        const persistDebounced = debounce(() => {
            const all = loadState();
            const cur = all.find((t) => t.id === loadActive());
            if (!cur) return;
            captureInto(cur);
            saveState(all);
        }, 250);

        document.addEventListener('input', (e) => {
            if (e.target && e.target.closest('#fieldsContainer, #copies, #template_file')) {
                persistDebounced();
            }
        });
        document.addEventListener('change', (e) => {
            if (e.target && (e.target.id === 'template_file' || e.target.id === 'copies')) {
                persistDebounced();
            }
        });
    }

    function debounce(fn, ms) {
        let h;
        return function () {
            clearTimeout(h);
            h = setTimeout(fn, ms);
        };
    }

    document.addEventListener('DOMContentLoaded', bootstrap);
})();
