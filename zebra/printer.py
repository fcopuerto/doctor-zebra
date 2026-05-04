"""Cross-platform printer interactions for Zebra label printers.

Supported backends (auto-selected from the target string):

- ``tcp``       raw socket to ZPL port 9100. Target looks like ``IP`` or
                ``IP:PORT``. Works on macOS, Linux and Windows.
- ``windows``   Windows print spooler via ``pywin32``. Handles USB-connected
                Zebras installed through the Zebra driver, plus any printer
                visible to Windows. Target is the Windows printer name.
- ``cups``      ``lp``/``lpstat`` on macOS and Linux. Target is the CUPS
                queue name.

The target can also carry an explicit scheme (``tcp://``, ``win://``,
``cups://``) to force a backend.
"""

import logging
import socket
import subprocess
import sys
import time
from threading import Lock
from typing import Optional

# Status lookups (lpstat / winspool) are surprisingly expensive — 50-300 ms
# each — and the sidebar's `inject_printer_info` context processor calls
# `printer_status` on EVERY request. Cache the answer for a few seconds so
# back-to-back page loads don't pay the bill repeatedly.
_STATUS_CACHE: dict[str, tuple[float, tuple[str, str]]] = {}
_STATUS_CACHE_TTL = 5.0  # seconds
_STATUS_CACHE_LOCK = Lock()

IS_WINDOWS = sys.platform.startswith('win')
DEFAULT_ZPL_PORT = 9100
TCP_TIMEOUT = 5.0


class PrinterError(Exception):
    """Raised when a print backend fails to deliver a job."""


TEST_ZPL = (
    "^XA"
    "^CF0,40"
    "^FO40,40^FDZebra Test^FS"
    "^CF0,24"
    "^FO40,100^FDConnection OK^FS"
    "^FO40,140^FDPrinted from Zebra App^FS"
    "^XZ"
)


# ---------------------------------------------------------------------------
# Target parsing
# ---------------------------------------------------------------------------

def parse_target(target: str) -> tuple[str, str]:
    """Public wrapper around :func:`_parse_target`."""
    return _parse_target(target)


def split_host_port(remainder: str) -> tuple[str, int]:
    """Public wrapper around :func:`_split_host_port`."""
    return _split_host_port(remainder)


def _parse_target(target: str) -> tuple[str, str]:
    """Return ``(backend, remainder)`` for the supplied target string."""
    if not target:
        return ('none', '')

    t = target.strip()
    lower = t.lower()

    if lower.startswith('tcp://'):
        return ('tcp', t[6:])
    if lower.startswith('win://'):
        return ('windows', t[6:])
    if lower.startswith('cups://'):
        return ('cups', t[7:])

    if _looks_like_host_port(t):
        return ('tcp', t)

    return ('windows' if IS_WINDOWS else 'cups', t)


def _looks_like_host_port(value: str) -> bool:
    """Best-effort detection of ``host[:port]`` targets."""
    if '/' in value or ' ' in value:
        return False
    host, _, port = value.partition(':')
    if port and not port.isdigit():
        return False
    if not host:
        return False
    # IPv4 literal
    parts = host.split('.')
    if len(parts) == 4 and all(p.isdigit() and 0 <= int(p) <= 255 for p in parts):
        return True
    # Explicit port present → treat as network target (e.g. zebra.local:9100)
    if port:
        return True
    return False


def _split_host_port(remainder: str) -> tuple[str, int]:
    host, _, port = remainder.partition(':')
    return host, int(port) if port else DEFAULT_ZPL_PORT


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def send_to_printer(target: str, zpl: str, copies: int = 1) -> None:
    """Send raw ZPL to ``target``. Raises :class:`PrinterError` on failure."""
    backend, remainder = _parse_target(target)
    copies = max(1, int(copies or 1))

    if backend == 'tcp':
        host, port = _split_host_port(remainder)
        _send_tcp(host, port, zpl, copies)
    elif backend == 'windows':
        _send_windows(remainder, zpl, copies)
    elif backend == 'cups':
        _send_cups(remainder, zpl, copies)
    else:
        raise PrinterError('No printer target configured')


def list_system_printers(filter_keyword: str = 'zebra') -> list[str]:
    """Enumerate printers known to the OS. Returns an empty list on failure."""
    if IS_WINDOWS:
        return _list_windows_printers(filter_keyword)
    return _list_cups_printers(filter_keyword)


def test_target(target: str) -> tuple[bool, str]:
    """Fast connectivity check without printing anything.

    Returns ``(ok, message)``. Used by the config UI test button.
    """
    backend, remainder = _parse_target(target)

    if backend == 'none':
        return (False, 'No printer target configured')

    if backend == 'tcp':
        host, port = _split_host_port(remainder)
        try:
            with socket.create_connection((host, port), timeout=2.0):
                return (True, f'Reachable at {host}:{port}')
        except OSError as e:
            return (False, f'Cannot reach {host}:{port}: {e}')

    if backend == 'windows':
        try:
            win32print = _load_win32print()
        except PrinterError as e:
            return (False, str(e))
        try:
            handle = win32print.OpenPrinter(remainder)
            win32print.ClosePrinter(handle)
            return (True, f'Windows printer "{remainder}" is available')
        except Exception as e:
            return (False, f'Windows printer check failed: {e}')

    if backend == 'cups':
        status, color = _cups_status(remainder)
        ok = color in ('green', 'blue')
        return (ok, status)

    return (False, 'Unknown backend')


def print_test_label(target: str) -> None:
    """Send a tiny ZPL test label to ``target``. Raises :class:`PrinterError`."""
    send_to_printer(target, TEST_ZPL, copies=1)


def printer_status(target: str) -> tuple[str, str]:
    """Return ``(status_text, color)`` for UI display, cached for ~5s.

    Each backend's underlying status call (lpstat, winspool, TCP probe)
    can take 50-300 ms; running it on every page render kept the sidebar
    feeling sluggish. Successive calls within the TTL get the cached
    result; a stale entry triggers a fresh probe.
    """
    if not target:
        return ('Not configured', 'gray')

    now = time.monotonic()
    with _STATUS_CACHE_LOCK:
        hit = _STATUS_CACHE.get(target)
        if hit and (now - hit[0]) < _STATUS_CACHE_TTL:
            return hit[1]

    result = _printer_status_uncached(target)
    with _STATUS_CACHE_LOCK:
        _STATUS_CACHE[target] = (now, result)
    return result


def _printer_status_uncached(target: str) -> tuple[str, str]:
    """The actual backend dispatch, without the cache."""
    backend, remainder = _parse_target(target)

    if backend == 'tcp':
        host, port = _split_host_port(remainder)
        return _tcp_status(host, port)
    if backend == 'windows':
        return _windows_status(remainder)
    if backend == 'cups':
        return _cups_status(remainder)
    return ('Unknown', 'gray')


# ---------------------------------------------------------------------------
# TCP backend (port 9100)
# ---------------------------------------------------------------------------

def _send_tcp(host: str, port: int, zpl: str, copies: int) -> None:
    payload = (zpl * copies).encode('utf-8')
    try:
        with socket.create_connection((host, port), timeout=TCP_TIMEOUT) as sock:
            sock.sendall(payload)
    except OSError as e:
        logging.error(f"TCP print to {host}:{port} failed: {e}")
        raise PrinterError(f"Cannot reach printer at {host}:{port}: {e}") from e


def _tcp_status(host: str, port: int) -> tuple[str, str]:
    try:
        with socket.create_connection((host, port), timeout=2.0):
            return ('Online', 'green')
    except OSError:
        return ('Offline', 'red')


# ---------------------------------------------------------------------------
# Windows backend (pywin32)
# ---------------------------------------------------------------------------

def _load_win32print():
    try:
        import win32print  # type: ignore
        return win32print
    except ImportError as e:
        raise PrinterError(
            'pywin32 is not installed. Run: pip install pywin32'
        ) from e


def _send_windows(name: str, zpl: str, copies: int) -> None:
    win32print = _load_win32print()
    payload = (zpl * copies).encode('utf-8')
    try:
        handle = win32print.OpenPrinter(name)
    except Exception as e:  # pywin32 raises pywintypes.error
        raise PrinterError(f"Cannot open Windows printer '{name}': {e}") from e
    try:
        job = win32print.StartDocPrinter(handle, 1, ('ZPL Label', None, 'RAW'))
        try:
            win32print.StartPagePrinter(handle)
            win32print.WritePrinter(handle, payload)
            win32print.EndPagePrinter(handle)
        finally:
            win32print.EndDocPrinter(handle)
        logging.info(f"Windows spooler accepted job {job} for '{name}'")
    except Exception as e:
        raise PrinterError(f"Windows print to '{name}' failed: {e}") from e
    finally:
        win32print.ClosePrinter(handle)


def _list_windows_printers(filter_keyword: str) -> list[str]:
    try:
        win32print = _load_win32print()
    except PrinterError as e:
        logging.error(str(e))
        return []

    # Enumerate local + connected printers
    flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
    try:
        raw = win32print.EnumPrinters(flags, None, 2)
    except Exception as e:
        logging.error(f"EnumPrinters failed: {e}")
        return []

    kw = (filter_keyword or '').lower()
    names: list[str] = []
    for info in raw:
        name = info.get('pPrinterName') if isinstance(info, dict) else None
        if not name:
            continue
        haystack = ' '.join(
            str(info.get(k, '')) for k in ('pPrinterName', 'pDriverName', 'pPortName')
        ).lower()
        if not kw or kw in haystack:
            names.append(name)
    return names


def _windows_status(name: str) -> tuple[str, str]:
    try:
        win32print = _load_win32print()
    except PrinterError as e:
        return (str(e), 'red')

    try:
        handle = win32print.OpenPrinter(name)
    except Exception as e:
        return (f"Not found: {e}", 'red')
    try:
        info = win32print.GetPrinter(handle, 2)
    except Exception as e:
        return (f"Error: {e}", 'red')
    finally:
        win32print.ClosePrinter(handle)

    status = info.get('Status', 0) if isinstance(info, dict) else 0
    jobs = info.get('cJobs', 0) if isinstance(info, dict) else 0

    # Common PRINTER_STATUS_* flags (winspool.h)
    offline = 0x00000080
    paused = 0x00000001
    error = 0x00000002
    out_of_paper = 0x00004000

    if status & offline:
        return ('Offline', 'red')
    if status & (paused | error | out_of_paper):
        return ('Error/Paused', 'red')
    if jobs and status == 0:
        return ('Printing', 'blue')
    return ('Idle', 'green')


# ---------------------------------------------------------------------------
# CUPS backend (macOS / Linux)
# ---------------------------------------------------------------------------

def _send_cups(name: str, zpl: str, copies: int) -> None:
    try:
        subprocess.run(
            ['lp', '-d', name, '-o', 'raw', '-n', str(copies)],
            input=zpl.encode('utf-8'),
            check=True,
        )
    except FileNotFoundError as e:
        raise PrinterError('lp command not found (install CUPS)') from e
    except subprocess.CalledProcessError as e:
        raise PrinterError(f"CUPS print to '{name}' failed: {e}") from e


def _list_cups_printers(filter_keyword: str) -> list[str]:
    try:
        result = subprocess.run(
            ['lpstat', '-p', '-l'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )
    except FileNotFoundError:
        logging.error('lpstat command not found')
        return []
    except subprocess.CalledProcessError as e:
        logging.error(f"Error executing lpstat: {e}")
        return []

    kw = (filter_keyword or '').lower()
    printers: list[str] = []
    current: Optional[str] = None
    is_match = False

    for line in result.stdout.splitlines():
        if line.startswith('printer '):
            if current and (not kw or is_match):
                printers.append(current)
            parts = line.split()
            current = parts[1] if len(parts) > 1 else None
            is_match = False
        if current and kw and kw in line.lower():
            is_match = True

    if current and (not kw or is_match):
        printers.append(current)
    return printers


def _cups_status(name: str) -> tuple[str, str]:
    try:
        result = subprocess.run(
            ['lpstat', '-p', name],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )
    except FileNotFoundError:
        return ('lpstat not installed', 'red')
    except subprocess.CalledProcessError as e:
        logging.error(f"Error getting printer status for {name}: {e}")
        return (f'Error: {e}', 'red')

    output = result.stdout.lower()
    if 'is idle' in output:
        return ('Idle', 'green')
    if 'is printing' in output:
        return ('Printing', 'blue')
    if 'disabled' in output or 'not enabled' in output:
        return ('Disabled', 'red')
    return ('Unknown', 'gray')
