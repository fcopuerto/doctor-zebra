"""LAN peer discovery for Comandante Zebra (mDNS / Bonjour).

Each running instance optionally publishes itself on the local network as
a ``_comandante-zebra._tcp.local.`` service so other instances can list
it in Settings → Network. The actual data transfer (templates, etc.)
goes through plain HTTP endpoints under ``/api/peer/*`` and is
authenticated with a per-instance PIN — see :mod:`zebra.network`.

Public API:

* :class:`Discovery` — start/stop the publisher + browser.
* :func:`get_peers` — return the current snapshot of known peers.

The browser is always on (so we can list peers even when we're not
broadcasting ourselves), but the publisher only runs when we know which
HTTP port Flask is listening on (``port`` in :meth:`Discovery.start`).
"""

from __future__ import annotations

import logging
import socket
from dataclasses import dataclass, field
from threading import Lock
from typing import Iterable

try:
    from zeroconf import (
        IPVersion,
        ServiceBrowser,
        ServiceInfo,
        ServiceListener,
        Zeroconf,
    )
    HAVE_ZEROCONF = True
except Exception as e:  # noqa: BLE001
    logging.warning(f'zeroconf unavailable, peer discovery disabled: {e}')
    HAVE_ZEROCONF = False
    # Fallbacks so the module still imports cleanly when zeroconf is
    # missing — Discovery.start() just becomes a no-op in that case.
    ServiceListener = object  # type: ignore[misc,assignment]
    ServiceBrowser  = None    # type: ignore[assignment]
    ServiceInfo     = None    # type: ignore[assignment]
    Zeroconf        = None    # type: ignore[assignment]
    IPVersion       = None    # type: ignore[assignment]


SERVICE_TYPE = '_comandante-zebra._tcp.local.'


@dataclass
class Peer:
    """A Comandante Zebra instance discovered on the LAN."""
    name: str          # service instance name (without ._comandante-zebra...)
    address: str       # IPv4
    port: int
    version: str = ''
    profile: str = ''
    properties: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            'name':    self.name,
            'address': self.address,
            'port':    self.port,
            'version': self.version,
            'profile': self.profile,
            'url':     f'http://{self.address}:{self.port}',
        }


class _Listener(ServiceListener):  # type: ignore[misc]
    """Maintains the live ``Discovery._peers`` map as services come and go."""

    def __init__(self, owner: 'Discovery') -> None:
        self.owner = owner

    def add_service(self, zc, type_, name):  # type: ignore[no-untyped-def]
        info = zc.get_service_info(type_, name)
        if info:
            self.owner._upsert(name, info)

    def update_service(self, zc, type_, name):  # type: ignore[no-untyped-def]
        info = zc.get_service_info(type_, name)
        if info:
            self.owner._upsert(name, info)

    def remove_service(self, zc, type_, name):  # type: ignore[no-untyped-def]
        self.owner._remove(name)


class Discovery:
    """Owns the Zeroconf instance, the publisher and the browser."""

    def __init__(self) -> None:
        self._zc: 'Zeroconf | None' = None
        self._browser: 'ServiceBrowser | None' = None
        self._info: 'ServiceInfo | None' = None
        self._peers: dict[str, Peer] = {}
        self._lock = Lock()
        # Service instance name we used when we registered ourselves;
        # filtered out of get_peers() so the local app doesn't show up
        # in its own list.
        self._self_name: str = ''
        # Diagnostics: the most recent error from init/publish (or None
        # on success). Used by /api/network/diagnostics so the UI can
        # tell the user "your firewall is probably blocking 5353/UDP".
        self._last_init_error: str | None = None
        self._last_publish_error: str | None = None
        self._published_port: int = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(
        self,
        peer_name: str,
        version: str,
        profile: str,
        port: int | None = None,
    ) -> None:
        """Start browsing the LAN. If ``port`` is given, also publish self.

        Idempotent — a second call replaces the previous registration so
        the announced port/profile/version stay current.
        """
        if not HAVE_ZEROCONF:
            self._last_init_error = (
                'zeroconf package not available — install it with '
                '`uv sync` or `pip install zeroconf`'
            )
            return
        self.stop()
        try:
            self._zc = Zeroconf(ip_version=IPVersion.V4Only)
            self._last_init_error = None
        except Exception as e:  # noqa: BLE001
            logging.warning(f'Zeroconf init failed, discovery disabled: {e}')
            self._last_init_error = str(e)
            self._zc = None
            return

        # Always browse; only publish when we have a port.
        listener = _Listener(self)
        self._browser = ServiceBrowser(self._zc, SERVICE_TYPE, listener)
        logging.info(f'mDNS browser started for {SERVICE_TYPE}')

        if port and port > 0:
            self._publish(peer_name, version, profile, port)

    def _publish(self, peer_name: str, version: str, profile: str, port: int) -> None:
        if self._zc is None:
            return
        ip = _local_ip_or_loopback()
        # Service instance must be unique on the network. The hostname
        # qualifier handles 99% of cases; we also append the port so two
        # instances on the same host don't collide.
        instance = f'{peer_name} ({port})'
        full_name = f'{instance}.{SERVICE_TYPE}'
        properties = {
            'name':    peer_name,
            'version': version,
            'profile': profile,
        }
        try:
            info = ServiceInfo(
                SERVICE_TYPE,
                full_name,
                addresses=[socket.inet_aton(ip)],
                port=port,
                properties=properties,
                server=f'{socket.gethostname()}.local.',
            )
            self._zc.register_service(info, allow_name_change=True)
            self._info = info
            self._self_name = full_name
            self._published_port = port
            self._last_publish_error = None
            logging.info(f'mDNS published as {full_name} at {ip}:{port}')
        except Exception as e:  # noqa: BLE001
            logging.warning(f'mDNS publish failed: {e}')
            self._info = None
            self._published_port = 0
            self._last_publish_error = str(e)

    def stop(self) -> None:
        if self._zc is None:
            return
        try:
            if self._info is not None:
                self._zc.unregister_service(self._info)
        except Exception:  # noqa: BLE001
            pass
        try:
            self._zc.close()
        except Exception:  # noqa: BLE001
            pass
        self._zc = None
        self._browser = None
        self._info = None
        self._self_name = ''
        with self._lock:
            self._peers.clear()

    # ------------------------------------------------------------------
    # Reads / writes — internal
    # ------------------------------------------------------------------

    def _upsert(self, full_name: str, info: 'ServiceInfo') -> None:
        if full_name == self._self_name:
            return  # don't list ourselves
        try:
            addresses = info.parsed_addresses() if hasattr(info, 'parsed_addresses') else []
            address = addresses[0] if addresses else ''
        except Exception:  # noqa: BLE001
            address = ''

        props: dict = {}
        for k, v in (info.properties or {}).items():
            try:
                props[k.decode() if isinstance(k, bytes) else str(k)] = (
                    v.decode() if isinstance(v, bytes) else str(v)
                )
            except Exception:  # noqa: BLE001
                pass

        peer = Peer(
            name=props.get('name', full_name.split('.', 1)[0]),
            address=address,
            port=info.port or 0,
            version=props.get('version', ''),
            profile=props.get('profile', ''),
            properties=props,
        )
        with self._lock:
            self._peers[full_name] = peer

    def _remove(self, full_name: str) -> None:
        with self._lock:
            self._peers.pop(full_name, None)

    # ------------------------------------------------------------------
    # Reads — public
    # ------------------------------------------------------------------

    def peers(self) -> list[Peer]:
        with self._lock:
            return sorted(self._peers.values(), key=lambda p: (p.name, p.address))

    def diagnostics(self) -> dict:
        """Return a status snapshot used by Settings → Network → Diagnostics.

        Includes everything needed to render actionable advice when peer
        discovery doesn't work — the typical culprits are firewall rules
        on UDP/5353 (mDNS), Bonjour Service missing on Windows, or the
        zeroconf package not being installed at all.
        """
        ip = _local_ip_or_loopback()
        zc_alive = self._zc is not None
        publishing = self._info is not None and self._published_port > 0
        browsing = self._browser is not None
        peer_count = 0
        with self._lock:
            peer_count = len(self._peers)

        advice: list[str] = []
        if not HAVE_ZEROCONF:
            advice.append('zeroconf_missing')
        elif self._last_init_error:
            advice.append('zeroconf_init_failed')
        elif self._last_publish_error:
            # Common on Windows when Bonjour Service isn't installed,
            # or when a firewall blocks UDP/5353 outbound.
            advice.append('publish_failed')
        else:
            if not publishing and self._published_port == 0:
                # Browser is up but we never tried to publish (no port).
                advice.append('not_publishing')
            if browsing and peer_count == 0:
                # Listening but seeing nobody. Could be: alone on the LAN,
                # firewall blocks inbound mDNS, or different subnet.
                advice.append('no_peers_seen')
            if ip in ('127.0.0.1', '0.0.0.0'):
                advice.append('no_lan_ip')

        return {
            'zeroconf_available': HAVE_ZEROCONF,
            'browser_active':    browsing,
            'publisher_active':  publishing,
            'published_port':    self._published_port,
            'local_ip':          ip,
            'init_error':        self._last_init_error,
            'publish_error':     self._last_publish_error,
            'peer_count':        peer_count,
            'advice':            advice,
        }


# Module-level singleton — Flask only ever needs one instance.
_DISCOVERY = Discovery()


def get_discovery() -> Discovery:
    return _DISCOVERY


def get_peers() -> list[Peer]:
    return _DISCOVERY.peers()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _local_ip_or_loopback() -> str:
    """Best-effort local LAN IP. Falls back to 127.0.0.1 so things still work
    on a host with no network."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(0.5)
            # Doesn't actually send anything to 8.8.8.8 — just resolves the
            # outbound interface that would be used.
            s.connect(('8.8.8.8', 80))
            return s.getsockname()[0]
    except Exception:  # noqa: BLE001
        return '127.0.0.1'


def local_ip() -> str:
    """Public helper used by the Network UI to show 'my address'."""
    return _local_ip_or_loopback()
