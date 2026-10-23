"""Make sure the game is offline before the bot plays.

The bot is meant to run on a dummy account with a game that cannot reach the
internet. This module only *checks*: it lists the network connections owned
by BloonsTD6.exe (Windows' Get-NetTCPConnection) and reports the game as
online when any of them is an established connection to a non-local address.
It never changes network or firewall settings; blocking the game is done
once by the user, e.g. with an outbound Windows Firewall rule for
BloonsTD6.exe (see README, "Offline play").

Override for testing: create a file named ALLOW_ONLINE in the project folder.
"""
import ipaddress
import json
import logging
import subprocess
from pathlib import Path

log = logging.getLogger("offline")

ROOT = Path(__file__).resolve().parents[1]
ALLOW_ONLINE_FILE = ROOT / "ALLOW_ONLINE"

_PS = (
    "$p = Get-Process BloonsTD6 -ErrorAction SilentlyContinue | Select-Object -First 1; "
    "if ($p) { Get-NetTCPConnection -OwningProcess $p.Id -State Established -ErrorAction SilentlyContinue "
    "| Select-Object RemoteAddress, RemotePort | ConvertTo-Json -Compress }"
)


def _is_remote(address):
    """True for an internet address (not loopback, link-local or private LAN)."""
    try:
        ip = ipaddress.ip_address(address.split("%")[0])
    except ValueError:
        return True  # unknown format: be strict
    return not (ip.is_loopback or ip.is_link_local or ip.is_private or ip.is_unspecified)


def game_connections():
    """[(address, port)] of the game's established connections to the internet.
    None when the check itself failed (PowerShell missing, timeout)."""
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", _PS],
                             capture_output=True, text=True, timeout=20, creationflags=subprocess.CREATE_NO_WINDOW).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    if not out:
        return []
    rows = json.loads(out)
    rows = rows if isinstance(rows, list) else [rows]
    return [(r["RemoteAddress"], r["RemotePort"]) for r in rows if _is_remote(r["RemoteAddress"])]


def check():
    """(ok, reason): ok is True when the bot may play."""
    if ALLOW_ONLINE_FILE.exists():
        return True, "ALLOW_ONLINE file present - offline check skipped"
    conns = game_connections()
    if conns is None:
        return False, "could not check the game's network connections"
    if conns:
        shown = ", ".join(f"{a}:{p}" for a, p in conns[:4])
        return False, f"the game is online ({len(conns)} internet connections: {shown})"
    return True, "game is offline"
