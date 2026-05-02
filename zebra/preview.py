"""Labelary preview client (renders ZPL to PNG)."""

import logging

import requests

from zebra.constants import LABELARY_URL, REQUEST_TIMEOUT


def zpl_to_png(zpl: str, timeout: int = REQUEST_TIMEOUT) -> bytes | None:
    try:
        response = requests.post(
            LABELARY_URL,
            data=zpl.encode('utf-8'),
            headers={'Accept': 'image/png'},
            timeout=timeout,
        )
        response.raise_for_status()
        return response.content
    except requests.RequestException as e:
        logging.error(f"Error converting ZPL to image: {e}")
        return None
