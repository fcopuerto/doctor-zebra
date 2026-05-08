"""Labelary preview client (renders ZPL to PNG)."""

import logging

import requests

from zebra.constants import (
    LABELARY_DPMM, LABELARY_FALLBACK_SIZE, LABELARY_URL_TEMPLATE,
    REQUEST_TIMEOUT,
)
from zebra.zpl import label_dimensions_mm


_MM_PER_INCH = 25.4


def _size_from_zpl(zpl: str) -> str:
    """Return the Labelary ``WxH`` size token (inches) parsed from the ZPL.

    Falls back to :data:`LABELARY_FALLBACK_SIZE` when ``^PW``/``^LL`` are
    missing or non-positive — better to render in a 4x4 canvas than to
    throw away the preview entirely.
    """
    width_mm, height_mm = label_dimensions_mm(zpl)
    if not width_mm or not height_mm or width_mm <= 0 or height_mm <= 0:
        return LABELARY_FALLBACK_SIZE
    # Labelary accepts decimals; round to 2 places to keep the URL tidy.
    w_in = round(width_mm / _MM_PER_INCH, 2)
    h_in = round(height_mm / _MM_PER_INCH, 2)
    return f'{w_in}x{h_in}'


def zpl_to_png(zpl: str, timeout: int = REQUEST_TIMEOUT) -> bytes | None:
    url = LABELARY_URL_TEMPLATE.format(
        dpmm=LABELARY_DPMM,
        size=_size_from_zpl(zpl),
    )
    try:
        response = requests.post(
            url,
            data=zpl.encode('utf-8'),
            headers={'Accept': 'image/png'},
            timeout=timeout,
        )
        response.raise_for_status()
        return response.content
    except requests.RequestException as e:
        logging.error(f"Error converting ZPL to image: {e}")
        return None
