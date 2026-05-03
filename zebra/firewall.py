"""Cross-platform helpers to open the firewall for mDNS (UDP 5353).

Only Windows really needs hand-holding here:

* **macOS** uses pf with sane defaults and Bonjour is part of the OS, so
  mDNS works out of the box; nothing to do.
* **Linux** is a wild west of UFW / firewalld / iptables — better to
  show the user the exact command to run and let them apply it under
  their own setup.
* **Windows** has Defender Firewall blocking inbound by default. The
  user normally gets a UAC popup the first time something tries to
  open a port, but our Flask process runs on a random local port and
  mDNS uses 5353/UDP, which Defender doesn't auto-prompt for. So we
  expose an in-app "open firewall" button that fires PowerShell with
  elevation to add the right rules.

The PowerShell snippet is idempotent: if a rule with the same display
name already exists it's removed and re-added so the parameters stay
in sync with this version of the app.
"""

from __future__ import annotations

import logging
import platform
import subprocess
import sys


def is_windows() -> bool:
    return sys.platform == 'win32'


# Display name used for both inbound and outbound rules. We keep them
# stable so subsequent runs find and refresh the existing rules instead
# of stacking duplicates.
RULE_DISPLAY_NAME = 'Comandante Zebra (mDNS)'


# PowerShell that we run elevated. Removes any previous rule with our
# name, then adds inbound + outbound on UDP/5353. Wrapped in try/catch
# so the elevated window doesn't just flash and disappear on error.
_PS_SCRIPT = f'''
$ErrorActionPreference = 'Stop'
try {{
    $name = '{RULE_DISPLAY_NAME}'
    Get-NetFirewallRule -DisplayName $name -ErrorAction SilentlyContinue | Remove-NetFirewallRule -ErrorAction SilentlyContinue
    New-NetFirewallRule -DisplayName $name -Direction Inbound  -Protocol UDP -LocalPort 5353 -Action Allow -Profile Any | Out-Null
    New-NetFirewallRule -DisplayName $name -Direction Outbound -Protocol UDP -LocalPort 5353 -Action Allow -Profile Any | Out-Null
    Write-Host 'OK'
}} catch {{
    Write-Host "ERROR: $_"
    Read-Host 'Press Enter to close'
    exit 1
}}
'''


def open_mdns_windows() -> tuple[bool, str]:
    """Trigger an elevated PowerShell that creates/refreshes the rules.

    Returns ``(launched, message)``. ``launched`` is True if we managed
    to *kick off* the elevated process — we can't actually wait for the
    UAC dialog or the rule creation result from a non-elevated parent,
    so the message is a hint, not a confirmation.
    """
    if not is_windows():
        return (False, 'Not running on Windows.')

    # Build the launcher: a non-elevated PowerShell that uses
    # Start-Process -Verb RunAs to spawn an elevated child running
    # the script above. We base64-encode the inner script so quoting
    # is bulletproof.
    import base64
    encoded = base64.b64encode(_PS_SCRIPT.encode('utf-16-le')).decode('ascii')
    launcher = (
        "Start-Process -FilePath powershell.exe -Verb RunAs "
        "-ArgumentList '-NoProfile','-ExecutionPolicy','Bypass',"
        f"'-EncodedCommand','{encoded}'"
    )

    try:
        # No window for the launcher itself; UAC and the elevated child
        # are visible to the user.
        flags = 0x08000000 if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
        subprocess.Popen(
            ['powershell.exe', '-NoProfile', '-Command', launcher],
            creationflags=flags,
        )
    except OSError as e:
        logging.warning(f'Could not launch elevated firewall helper: {e}')
        return (False, f'Could not launch PowerShell: {e}')

    return (
        True,
        'Launched elevated firewall helper. Approve the UAC prompt to '
        f'add/refresh the "{RULE_DISPLAY_NAME}" rule.',
    )


def manual_instructions() -> dict:
    """Return the OS-specific copy-pasteable command for the user.

    For Linux/macOS or when the user doesn't want UAC, this is the
    fallback shown in the UI.
    """
    if is_windows():
        return {
            'os': 'windows',
            'shell': 'PowerShell (as Administrator)',
            'command': (
                f'New-NetFirewallRule -DisplayName "{RULE_DISPLAY_NAME}" '
                '-Direction Inbound -Protocol UDP -LocalPort 5353 -Action Allow; '
                f'New-NetFirewallRule -DisplayName "{RULE_DISPLAY_NAME}" '
                '-Direction Outbound -Protocol UDP -LocalPort 5353 -Action Allow'
            ),
        }
    if sys.platform == 'darwin':
        return {
            'os': 'macos',
            'shell': 'No action needed — macOS allows mDNS by default.',
            'command': '',
        }
    # Linux: pick the most likely tool and offer it. UFW + firewalld are
    # the two common high-level wrappers; fall back to iptables.
    return {
        'os': 'linux',
        'shell': 'sh (as root)',
        'command': (
            '# UFW:        sudo ufw allow 5353/udp\n'
            '# firewalld:  sudo firewall-cmd --add-port=5353/udp --permanent && sudo firewall-cmd --reload\n'
            '# iptables:   sudo iptables -A INPUT -p udp --dport 5353 -j ACCEPT'
        ),
    }


def os_info() -> dict:
    """Tiny helper for the UI to know which platform we're on."""
    return {
        'platform':  sys.platform,
        'is_windows': is_windows(),
        'is_macos':   sys.platform == 'darwin',
        'is_linux':   sys.platform.startswith('linux'),
        'release':    platform.release(),
    }
