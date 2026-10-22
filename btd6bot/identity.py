"""Which BTD6 account is signed in, and one state file per account.

The Settings screen prints "... / User ID: VXORVHFCB" along its bottom edge.
The runner reads it at session start and every few games; a different ID
means another save is loaded (e.g. a higher-level account), so its own state
file is loaded - or created and fully re-synced from the game.
"""
import logging
import re
import shutil
import time
from pathlib import Path

from .account import AccountState

log = logging.getLogger("identity")

ROOT = Path(__file__).resolve().parents[1]
ACCOUNTS = ROOT / "data" / "accounts"
LEGACY = ROOT / "data" / "account.json"     # single-account file from before
CURRENT = ROOT / "data" / "current_account.txt"

GEAR = (0.044, 0.196)          # settings button on the main menu
BACK = (0.044, 0.055)
ID_REGION = (0.2, 0.93, 0.8, 0.995)


def parse_user_id(text):
    m = re.search(r"user\s*id\s*[:;]?\s*([A-Za-z0-9]{6,})", text, re.I)
    if not m:
        return None
    # one canonical spelling for OCR look-alikes, so a misread never looks like
    # a different account
    return m.group(1).upper().translate(str.maketrans("0158", "OISB"))


def read_user_id(screen, inp, menus):
    """Main menu -> Settings -> read the User ID -> back. None if unreadable."""
    if menus.identify() != "main_menu":
        return None
    inp.click(*GEAR)
    uid = None
    end = time.time() + 5
    while time.time() < end and uid is None:
        time.sleep(0.4)
        words = menus.v.read(ID_REGION)
        uid = parse_user_id(" ".join(w.text for w in sorted(words, key=lambda w: w.x)))
    inp.click(*BACK)
    menus.wait_for("main_menu", timeout=5)
    # OCR confuses O/0 in IDs; keep the raw read but normalise the obvious one
    return uid


def account_path(uid):
    return ACCOUNTS / f"{uid}.json"


def load_for(uid):
    """(AccountState, is_new). Migrates the legacy single file to the first ID seen."""
    ACCOUNTS.mkdir(parents=True, exist_ok=True)
    path = account_path(uid)
    is_new = False
    if not path.exists():
        if LEGACY.exists() and not any(ACCOUNTS.glob("*.json")):
            shutil.copy2(LEGACY, path)
            log.info("migrated %s to account %s", LEGACY.name, uid)
        else:
            is_new = True
            log.warning("new account %s: starting fresh and syncing from the game", uid)
    acct = AccountState.load(path)
    # achievements progress is per account too
    from . import achievements
    ach = ACCOUNTS / f"{uid}.achievements.json"
    if not ach.exists() and achievements.STATE.exists() and achievements.STATE.parent == ACCOUNTS.parent             and not is_new:
        shutil.copy2(achievements.STATE, ach)
    achievements.STATE = ach
    try:
        CURRENT.write_text(uid, encoding="utf-8")
    except OSError:
        pass
    return acct, is_new


def current_path():
    """State file of the last account the bot saw (for tools / bot.py status)."""
    try:
        uid = CURRENT.read_text(encoding="utf-8").strip()
        if uid:
            return account_path(uid)
    except OSError:
        pass
    return LEGACY


SYNC_EVERY = 24 * 3600


def _sync_file(uid):
    return ACCOUNTS / f"{uid}.synced"


def is_stale(uid):
    try:
        return time.time() - float(_sync_file(uid).read_text().strip()) > SYNC_EVERY
    except (OSError, ValueError):
        return True


def mark_synced(uid):
    try:
        _sync_file(uid).write_text(str(time.time()))
    except OSError:
        pass
