"""Account identity: User ID parsing and per-account state files (temp dirs only)."""
import sys
import tempfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from btd6bot import identity as I  # noqa: E402


def test_parse_user_id_normalises_lookalikes():
    a = I.parse_user_id("(c) Ninja Kiwi Version 57.3.12207 / User ID: VXORVHFCB")
    b = I.parse_user_id("Ninja KiwiVersion57.3.12207 / UserID: VX0RVHFCB")
    assert a == b == "VXORVHFCB"
    assert I.parse_user_id("no id here") is None


def test_new_account_gets_its_own_file_and_needs_sync():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        with mock.patch.object(I, "ACCOUNTS", d / "accounts"), \
                mock.patch.object(I, "LEGACY", d / "account.json"), \
                mock.patch.object(I, "CURRENT", d / "current.txt"):
            acct, new = I.load_for("AAAAAAAA")
            assert new and acct.player_level == 1
            acct.player_level = 40
            acct.save()
            assert I.is_stale("AAAAAAAA")
            I.mark_synced("AAAAAAAA")
            assert not I.is_stale("AAAAAAAA")
            again, new2 = I.load_for("AAAAAAAA")
            assert not new2 and again.player_level == 40
            other, new3 = I.load_for("BBBBBBBB")
            assert new3 and other.player_level == 1
            assert I.current_path() == d / "accounts" / "BBBBBBBB.json"


if __name__ == "__main__":
    test_parse_user_id_normalises_lookalikes()
    test_new_account_gets_its_own_file_and_needs_sync()
    print("ok")
