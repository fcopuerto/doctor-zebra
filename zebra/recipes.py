"""Label *recipes* — parametric ZPL generators for the label wizard.

A recipe is a pure function: structured options in, a complete ``^XA…^XZ``
ZPL string out. No I/O, no Flask — trivially unit-testable and reusable by
both the live-preview endpoint and the "save as template" path.

The first recipe is the **WiFi QR** label. The QR payload is *baked* (the
WiFi-escaping is applied here, once) rather than left as a print-time
``{token}``: ``zpl.render`` does not apply WiFi escaping, so a password
containing ``; , : \\ "`` left as a token would produce a QR that phones
cannot parse. For a courtesy WiFi label a valid QR matters more than
print-time editability — re-run the wizard to change the network.
"""

from __future__ import annotations

# 203 dpi printers (e.g. Zebra ZD420-203dpi): 8 dots per millimetre.
DOTS_PER_MM = 8

# QR positions. Keys are stable (used by the UI + form); values are the
# (horizontal, vertical) intent used by the anchor maths below.
ANCHORS = (
    'top-left', 'top-center', 'top-right',
    'mid-left', 'center', 'mid-right',
    'bottom-left', 'bottom-center', 'bottom-right',
)

# QR error-correction levels, low→high. Higher = more robust but bigger.
EC_LEVELS = ('L', 'M', 'Q', 'H')


def _esc_wifi(value: str) -> str:
    r"""Escape a value for a ``WIFI:`` QR payload.

    Per the de-facto spec implemented by Android/iOS camera apps, the
    characters ``\ ; , : "`` are backslash-escaped. Backslash first so we
    don't double-escape the escapes we just added.
    """
    out = (value or '')
    out = out.replace('\\', '\\\\')
    for ch in (';', ',', ':', '"'):
        out = out.replace(ch, '\\' + ch)
    return out


def wifi_payload(ssid: str, password: str, security: str,
                 hidden: bool = False) -> str:
    """Build the standard ``WIFI:`` QR payload string.

    ``security``: ``WPA`` (covers WPA/WPA2/WPA3), ``WEP`` or ``nopass``
    (open network). Open networks carry no password.
    """
    sec = (security or 'WPA').strip().upper()
    if sec in ('', 'NONE', 'OPEN', 'NOPASS'):
        sec = 'nopass'
    elif sec not in ('WPA', 'WEP'):
        sec = 'WPA'

    parts = [f'T:{sec}', f'S:{_esc_wifi(ssid)}']
    if sec != 'nopass':
        parts.append(f'P:{_esc_wifi(password)}')
    if hidden:
        parts.append('H:true')
    return 'WIFI:' + ';'.join(parts) + ';;'


def _estimate_qr_side_dots(payload_len: int, ec: str, mag: int) -> int:
    """Rough printed QR side in dots — only used to place the anchor.

    We can't know the exact QR version without encoding, so estimate the
    module count from payload length + EC level. The live preview is the
    real source of truth; this just keeps the QR on-label as a sane
    starting point before the user nudges the offsets.
    """
    # Heuristic module counts for typical WiFi payloads (~30–90 chars).
    base = 25 + max(0, payload_len - 20) // 6 * 4   # ~25→~57 modules
    ec_bump = {'L': 0, 'M': 4, 'Q': 8, 'H': 12}.get(ec, 4)
    modules = min(85, base + ec_bump)
    return modules * max(1, mag)


def _anchor_xy(anchor: str, label_w: int, label_h: int,
                qr_side: int, margin: int) -> tuple[int, int]:
    """Top-left ``^FO`` coordinates for ``anchor`` within the label."""
    free_w = max(0, label_w - qr_side)
    free_h = max(0, label_h - qr_side)

    if 'left' in anchor:
        x = margin
    elif 'right' in anchor:
        x = max(margin, free_w - margin)
    else:
        x = free_w // 2

    if anchor.startswith('top'):
        y = margin
    elif anchor.startswith('bottom'):
        y = max(margin, free_h - margin)
    else:
        y = free_h // 2
    return (x, y)


def wifi_qr_zpl(
    *,
    ssid: str,
    password: str = '',
    security: str = 'WPA',
    hidden: bool = False,
    label_w_mm: float = 50.0,
    label_h_mm: float = 50.0,
    qr_anchor: str = 'center',
    qr_offset_x_mm: float = 0.0,
    qr_offset_y_mm: float = 0.0,
    qr_magnification: int = 5,
    qr_ec: str = 'M',
    caption: str = '',
    caption_below: bool = True,
    caption_font: int = 28,
) -> str:
    """Generate a complete WiFi-QR label as ZPL.

    Coordinates are computed for a 203 dpi printer. The anchor places the
    QR; the millimetre offsets nudge it from there.
    """
    label_w = max(1, round(label_w_mm * DOTS_PER_MM))
    label_h = max(1, round(label_h_mm * DOTS_PER_MM))
    mag = min(10, max(1, int(qr_magnification or 5)))
    ec = (qr_ec or 'M').strip().upper()
    if ec not in EC_LEVELS:
        ec = 'M'
    anchor = qr_anchor if qr_anchor in ANCHORS else 'center'
    margin = round(2 * DOTS_PER_MM)  # 2 mm safe margin

    payload = wifi_payload(ssid, password, security, hidden)
    qr_side = _estimate_qr_side_dots(len(payload), ec, mag)

    x, y = _anchor_xy(anchor, label_w, label_h, qr_side, margin)
    x += round(qr_offset_x_mm * DOTS_PER_MM)
    y += round(qr_offset_y_mm * DOTS_PER_MM)
    x = max(0, min(x, label_w - 1))
    y = max(0, min(y, label_h - 1))

    lines = [
        '^XA',
        f'^PW{label_w}',
        f'^LL{label_h}',
        '^CI28',                                  # UTF-8 (accented SSIDs)
        f'^FO{x},{y}^BQN,2,{mag}^FD{ec}A,{payload}^FS',
    ]

    cap = (caption or '').strip()
    if cap:
        fh = max(12, int(caption_font or 28))
        if caption_below:
            cap_y = min(label_h - fh - margin, y + qr_side + round(2 * DOTS_PER_MM))
        else:
            cap_y = max(margin, y - fh - round(2 * DOTS_PER_MM))
        cap_y = max(0, cap_y)
        # ^FB centres the text across the full label width.
        lines.append(
            f'^FO0,{cap_y}^A0N,{fh},{fh}^FB{label_w},2,0,C^FD{_clean_caption(cap)}^FS'
        )

    lines.append('^XZ')
    return '\n'.join(lines) + '\n'


def _clean_caption(text: str) -> str:
    """Strip ZPL control chars so caption text can't break the format."""
    return (text or '').replace('^', '').replace('~', '').strip()
