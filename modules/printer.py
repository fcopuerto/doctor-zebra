"""
Printer communication utilities.

Sends ZPL (Zebra Programming Language) data to a Zebra printer over a raw
TCP socket (the standard Zebra network printing protocol, port 9100).
"""
import re
import socket


def send_zpl(host: str, port: int, zpl: str, timeout: float = 10.0) -> None:
    """Open a TCP connection to *host*:*port* and send *zpl* as UTF-8 bytes.

    Raises:
        OSError: if the connection cannot be established or times out.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        sock.connect((host, port))
        sock.sendall(zpl.encode("utf-8"))


def render_template(template_str: str, data: dict) -> str:
    """Replace ``{variable}`` placeholders in *template_str* with values from
    *data*.

    Unknown placeholders (keys absent from *data*) are left unchanged so that
    partial rendering is safe.

    Example::

        >>> render_template("^FD{nombre}^FS", {"nombre": "Alice"})
        '^FDAlice^FS'
    """
    result = template_str
    for key, value in data.items():
        result = result.replace("{" + key + "}", str(value))
    return result


def extract_variables(template_str: str) -> list:
    """Return a sorted list of unique variable names found in *template_str*.

    A variable is any identifier enclosed in single curly braces, e.g.
    ``{nombre}``.

    Example::

        >>> extract_variables("^FD{nombre}^FS^FD{codigo}^FS^FD{nombre}^FS")
        ['codigo', 'nombre']
    """
    return sorted(set(re.findall(r"\{(\w+)\}", template_str)))
