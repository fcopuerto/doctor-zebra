"""Shared constants for the Zebra label app."""

# Labelary renders ZPL → PNG. The URL is built per-call so we can pass
# the actual label size (parsed from ``^PW``/``^LL``) instead of a fixed
# canvas, but we keep a fallback for ZPL fragments that don't carry
# dimensions (e.g. snippets in the version diff viewer).
LABELARY_DPMM = 8                                # 8 dots/mm = 203 dpi
LABELARY_FALLBACK_SIZE = '4x4'                   # inches, used when size is unknown
LABELARY_URL_TEMPLATE = (
    'http://api.labelary.com/v1/printers/{dpmm}dpmm/labels/{size}/0/'
)
REQUEST_TIMEOUT = 10
MAX_COPIES = 100
