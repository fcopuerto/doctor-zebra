/* Update notifier (passive).
 *
 * Hits /api/update/check (which is server-side cached for 24h, so this
 * is cheap to call on every page load). If a newer release exists and
 * the user hasn't dismissed it, the small badge in the sidebar footer
 * lights up. Click → modal with the release notes + Download button.
 */
(function () {
    'use strict';

    let latestInfo = null;

    async function checkUpdate() {
        try {
            const r = await fetch('/api/update/check');
            if (!r.ok) return;
            const data = await r.json();
            latestInfo = data;
            renderBadge(data);
        } catch (e) { /* offline → silent */ }
    }

    function renderBadge(d) {
        const badge = document.getElementById('updateBadge');
        if (!badge) return;
        if (!d.update_available) {
            badge.hidden = true;
            return;
        }
        badge.hidden = false;
        const label = badge.querySelector('.update-badge__label');
        if (label) label.textContent = '→ v' + d.latest;
        badge.title = 'v' + d.latest + ' available';
    }

    function openDialog() {
        if (!latestInfo) return;
        const dlg = document.getElementById('updateDialog');
        if (!dlg) return;
        document.getElementById('updateLatest').textContent = 'v' + (latestInfo.latest || '?');
        const pub = latestInfo.latest_published || '';
        document.getElementById('updatePublished').textContent =
            pub ? '· ' + pub.slice(0, 10) : '';
        document.getElementById('updateNotes').textContent =
            latestInfo.latest_notes || '(no release notes)';
        const dl = document.getElementById('updateDownload');
        if (dl) {
            dl.href = latestInfo.latest_url || '#';
            dl.target = '_blank';
            dl.rel = 'noopener';
        }
        if (typeof dlg.showModal === 'function') dlg.showModal();
        else dlg.setAttribute('open', '');
    }

    function closeDialog() {
        const dlg = document.getElementById('updateDialog');
        if (!dlg) return;
        if (typeof dlg.close === 'function') dlg.close();
        else dlg.removeAttribute('open');
    }

    async function dismissCurrent() {
        if (!latestInfo || !latestInfo.latest) {
            closeDialog();
            return;
        }
        try {
            await fetch('/api/update/dismiss', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ version: latestInfo.latest }),
            });
            // Local state: hide the badge for this session immediately.
            const badge = document.getElementById('updateBadge');
            if (badge) badge.hidden = true;
        } catch (e) { /* swallow */ }
        closeDialog();
    }

    document.addEventListener('DOMContentLoaded', function () {
        // Wire badge + dialog buttons.
        const badge = document.getElementById('updateBadge');
        if (badge) badge.addEventListener('click', openDialog);
        const close = document.getElementById('updateDialogClose');
        if (close) close.addEventListener('click', closeDialog);
        const dismiss = document.getElementById('updateDismiss');
        if (dismiss) dismiss.addEventListener('click', dismissCurrent);
        // Kick off the check after a short delay so the page paints first.
        setTimeout(checkUpdate, 800);
    });
})();
