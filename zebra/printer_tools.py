"""Catalogue of one-shot ZPL "tools" exposed in Settings → Tools.

Each tool is a tiny ZPL/control snippet that the printer interprets
on receipt — diagnostics (~WC), calibration (~JC), maintenance (~JR),
quick test prints, etc. These are the same things vendors usually hide
behind "hold Feed for 3 seconds" or "send via Zebra Setup Utilities";
having them as buttons in the app saves a lot of grief.

The goal is unidirectional fire-and-forget: send the bytes, trust the
printer to execute. Bidirectional commands (~HI, ~HQ…) need a TCP/USB
back-channel that we don't have for every backend; keeping those out
for now.
"""

from __future__ import annotations

# Each tool: ``id`` is the stable key used by API + i18n. ``group`` is
# only used to bucket them in the UI. ``zpl`` is what we actually send
# to the printer. ``confirm`` toggles a JS confirm() before firing.
TOOLS: list[dict] = [
    # ---- Diagnostics (printer prints stuff we can read) -----------------
    {
        'id': 'config_label',
        'group': 'diagnostics',
        'zpl': '~WC',
        'icon': 'i-info',
    },
    {
        'id': 'sensor_profile',
        'group': 'diagnostics',
        'zpl': '~JG',
        'icon': 'i-bar-chart',
    },
    {
        'id': 'network_config',
        'group': 'diagnostics',
        'zpl': '~WL',
        'icon': 'i-network',
    },

    # ---- Calibration ----------------------------------------------------
    {
        'id': 'calibrate_media',
        'group': 'calibration',
        # ~JC triggers the media sensor calibration; chain ^XA^JUS^XZ so
        # the new values are persisted to flash, not just to RAM.
        'zpl': '~JC\n^XA^JUS^XZ',
        'icon': 'i-refresh',
    },
    {
        'id': 'detect_label_length',
        'group': 'calibration',
        'zpl': '~JL',
        'icon': 'i-refresh',
    },

    # ---- Maintenance ----------------------------------------------------
    {
        'id': 'form_feed',
        'group': 'maintenance',
        # An empty ^XA…^XZ format makes the printer advance to the next
        # label boundary — same effect as pressing Feed once.
        'zpl': '^XA^XZ',
        'icon': 'i-printer',
    },
    {
        'id': 'save_settings',
        'group': 'maintenance',
        'zpl': '^XA^JUS^XZ',
        'icon': 'i-check',
    },
    {
        'id': 'reset_printer',
        'group': 'maintenance',
        'zpl': '~JR',
        'icon': 'i-refresh',
        'confirm': True,
    },

    # ---- Test print -----------------------------------------------------
    {
        'id': 'test_label',
        'group': 'test',
        # Self-contained test label. Uses the printer's persistent
        # PW/LL settings and ^MNN so it ignores web/mark sensor and
        # just prints what fits.
        'zpl': (
            '^XA'
            '^FO40,40^A0N,40,40^FDComandante Zebra^FS'
            '^FO40,90^A0N,25,25^FDPrint test OK^FS'
            '^FO40,130^A0N,20,20^FDIf you see this, the printer is alive.^FS'
            '^XZ'
        ),
        'icon': 'i-check',
    },
]


def by_id(tool_id: str) -> dict | None:
    for t in TOOLS:
        if t['id'] == tool_id:
            return t
    return None


def grouped() -> dict[str, list[dict]]:
    """Return tools indexed by group, in the order TOOLS defines them."""
    out: dict[str, list[dict]] = {}
    for t in TOOLS:
        out.setdefault(t['group'], []).append(t)
    return out


# Stable list of group ids in display order. Must match keys in i18n
# (tools.group.<id>).
GROUP_ORDER = ('diagnostics', 'calibration', 'maintenance', 'test')
