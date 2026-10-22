"""Top level: pick the next game, navigate to it, play it, record it, repeat."""
import logging
import time

import numpy as np

from . import layout as L
from . import progress
from . import towers as T
from .account import AccountState
from .achievements import Achievements
from .xpspend import forget_short, strategy_towers, sync_all, unlock_for_strategy
from .mk import Knowledge
from .identity import current_path, is_stale, load_for, mark_synced, read_user_id
from .choices import tower_chooser
from .game import Game
from .inputs import Aborted, FocusLost, Input
from .maplearn import MapModel
from .match import Match
from .menus import Menus
from .scanner import scan_placement, scan_water
from .screen import GameNotFound, Screen
from .strategy import Executor, coverage, hero_for, invested_cash, load_all, usable
from .vision import norm

log = logging.getLogger("runner")

MODE_BUTTON_TEXT = {
    "standard": "standard", "primary_only": "primaryonly", "deflation": "deflation",
    "military_only": "militaryonly", "apopalypse": "apopalypse", "reverse": "reverse",
    "magic_only": "magicmonkeysonly", "double_hp": "doublehpmoabs", "half_cash": "halfcash",
    "abr": "alternatebloonsrounds", "impoppable": "impoppable", "chimps": "chimps",
}

# mode button icon centres on each difficulty's mode screen (calibrated live
# 2026-10-21, 1920x1200); OCR misreads the two-line labels ("MAGIGMONKeYS")
MODE_BUTTON_POS = {
    "standard": (0.313, 0.55),
    "primary_only": (0.5, 0.42), "deflation": (0.688, 0.41),
    "military_only": (0.5, 0.42), "apopalypse": (0.688, 0.41), "reverse": (0.5, 0.68),
    "magic_only": (0.5, 0.42), "double_hp": (0.688, 0.42), "half_cash": (0.875, 0.42),
    "abr": (0.5, 0.69), "impoppable": (0.688, 0.69), "chimps": (0.875, 0.69),
}

ROOT_DIR = __import__("pathlib").Path(__file__).resolve().parents[1]
ID_CHECK_EVERY = 10                   # games between account (User ID) checks
ACH_EVERY = 24 * 3600                  # seconds between full achievement scans (badge claims in between)
PAUSE_FILE = ROOT_DIR / "PAUSE"        # create it to park the bot at the main menu
from .status import STATE_FILE, set_state  # noqa: E402,F401


ACH_STAMP = ROOT_DIR / "logs" / "achievements_scanned_at.txt"
# time of the full scan after which the ribbon's badge was still lit: the
# badge is then ignored until the next full scan (see _achievements_if_due)
ACH_MUTE = ROOT_DIR / "logs" / "achievements_badge_muted.txt"
MEDAL_SWEEP_EVERY = 24 * 3600          # seconds between map-select medal sweeps per account
# Waiting (nothing to play, an error loop, PAUSE): the supervisor's watchdog
# (run_forever.ps1) kills a bot whose logs/bot.log and logs/state.txt have not
# changed for 10 minutes, so long waits refresh the status this often.
IDLE_STATUS_EVERY = 120
IDLE_POLL = 5                          # seconds between checks for PAUSE / new code while waiting
# Consecutive game-loop errors, kept on disk so a restart does not reset them
ERROR_FILE = ROOT_DIR / "logs" / "error_streak.json"
ERROR_STREAK_WAIT = 3                  # the same error this many games in a row = a bot bug
ERROR_BENCH_AFTER = 2                  # failures of one map/mode before it is benched


def _read_stamp(path):
    """Unix time stored in a small text file, 0.0 if missing or unreadable."""
    try:
        return float(path.read_text().strip())
    except (OSError, ValueError):
        return 0.0


def _write_stamp(path, t):
    try:
        path.write_text(str(t))
    except OSError:
        pass


def _ach_last():
    return _read_stamp(ACH_STAMP)


def _ach_mark(t):
    _write_stamp(ACH_STAMP, t)


def _medal_sweep_file(uid):
    """Per account, next to its state file (like identity's .synced stamp)."""
    return ROOT_DIR / "data" / "accounts" / f"{uid}.medals_swept"


def _medal_sweep_due(uid, now=None):
    """Has this account's map-select medal sweep not run for a day?"""
    return (now or time.time()) - _read_stamp(_medal_sweep_file(uid)) > MEDAL_SWEEP_EVERY


def _load_errors():
    """{"sig": last error signature, "streak": times in a row, "maps":
    {"map|mode": failures}} from ERROR_FILE (empty when missing)."""
    import json
    try:
        d = json.loads(ERROR_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        d = {}
    return {"sig": d.get("sig"), "streak": int(d.get("streak", 0)), "maps": dict(d.get("maps", {}))}


def _save_errors(errors):
    import json
    try:
        ERROR_FILE.parent.mkdir(exist_ok=True)
        ERROR_FILE.write_text(json.dumps(errors, indent=1), encoding="utf-8")
    except OSError:
        pass


def _error_signature(e):
    """Which bug an exception is: its type and the bot function that raised
    it. The message is left out on purpose, as it may name the map: the same
    bug on 13 maps must count as one streak, not 13 different errors."""
    import traceback
    from pathlib import Path
    frames = [f for f in traceback.extract_tb(e.__traceback__) if "btd6bot" in f.filename]
    where = f"{Path(frames[-1].filename).name}:{frames[-1].name}" if frames else "?"
    return f"{type(e).__name__} in {where}"


def outside_cause(outcome, screen):
    """Why a game that was not won is not the map's (or the plan's) fault,
    else None. Such a game is neither recorded as a loss nor benched.
      * "abandoned": match.py saw the menus come back mid-game while the bot
        still had more than 20 lives (it calls that "abandoned", fewer is a
        "defeat"). Log evidence: Tree Stump medium ended at round 59 of 60
        with 149 lives (2026-10-22 01:39) and was benched 12 h as a loss.
      * the title or account screen after the game: someone signed in to
        another account mid-game (the game restarts to its title screen)."""
    if outcome == "abandoned":
        return "left the game with more than 20 lives"
    if screen in ("title", "account"):
        return f"the game went to the {screen} screen"
    return None


def tab_first_pages(reads):
    """Map-select category tab -> names on its first page, keeping only the
    tabs whose page is unambiguous. reads: {category: set of normalised
    names read right after clicking that tab}. Two tabs that read two or more
    of the same names did not both switch pages (a locked tab, a click lost
    in a transition): neither can tell its category apart, so both become
    empty. Before, the last of them won: Expert's read of the Beginner page
    put six Beginner maps under "expert" on both accounts."""
    out = dict(reads)
    for a in reads:
        for b in reads:
            if a < b and len(reads[a] & reads[b]) >= 2:
                out[a], out[b] = set(), set()
    return out


def page_category(keys, names, first_pages, current, known):
    """Category of one map-select page (every category starts on a new page,
    so a page holds a single category):
      1. the category of the known maps on it, when at least two agree and
         none disagrees (known: {map: category}, the game's own data),
      2. else the one tab whose first page shares two or more names with it,
      3. else the page continues the current category (None before any).
    keys: the page's normalised label texts; names: the maps they matched."""
    from collections import Counter
    votes = Counter(known[n] for n in names if n in known)
    if len(votes) == 1 and sum(votes.values()) >= 2:
        return next(iter(votes))
    tabs = [cat for cat, first in first_pages.items() if first and len(keys & first) >= 2]
    return tabs[0] if len(tabs) == 1 else current


def _code_imports():
    """Does the code on disk import (and do the strategies load) in a fresh interpreter?"""
    import subprocess
    import sys
    try:
        r = subprocess.run([sys.executable, "-c",
                            "import btd6bot.runner, btd6bot.strategy as s; s.load_all()"],
                           cwd=str(ROOT_DIR), capture_output=True, timeout=60)
        return r.returncode == 0
    except Exception:
        return False


def _code_stamp():
    """Latest modification time of the bot's code and strategy files."""
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    files = list((root / "btd6bot").glob("*.py")) + list((root / "strategies").rglob("*.yaml"))
    return max((f.stat().st_mtime for f in files), default=0)


def _tested(account, sid, mode):
    """Has this strategy won this mode on this account before?"""
    for key, st in (account.strategy_stats or {}).items():
        if sid in key and mode in key and st.get("wins", 0) > 0:
            return True
    return False


def planner_specs(strats, account):
    from .planner import StrategySpec
    from .strategy import achievement_strategies
    specs = []
    wanted = set(achievement_strategies(strats, Achievements.load()))
    for s in strats.values():
        p = s.get("planner") or {}
        allow = s["id"] in wanted
        if s.get("achievement") and not allow:
            continue  # achievement plans only while their achievement is wanted
        modes = [m for m in s.get("modes", []) if usable(s, m, account, allow_achievement=allow)[0]]
        # only modes whose threats (camo, lead, MOAB ... DDT) this build answers
        # with the upgrades this account has actually unlocked
        modes = [m for m in modes if coverage(s, m, account)[0]]
        if not modes:
            continue
        # Full upgrade requirements: the planner lowers the win chance for
        # upgrades not yet unlocked (unknown = locked), it no longer blocks.
        reqs = dict(p.get("towers") or {})
        base = {m: v for m, v in (p.get("base_success") or {}).items() if m in modes}
        hero = hero_for(s, account)
        if s.get("hero") and hero != s["hero"]:
            # the plan leans on a hero we do not own yet: be less sure of it
            base = {m: v * 0.85 for m, v in base.items()}
        # untested on this account: never trust a declared Hard+ prior above 0.85
        for m in base:
            if m not in ("easy", "primary_only", "medium") and not _tested(account, s["id"], m):
                base[m] = min(base[m], 0.85)
        specs.append(StrategySpec.from_any({
            "id": s["id"],
            "towers": reqs,
            "modes": modes,
            "base_success": base,
            "heroes": [hero],
            "achievement": s.get("achievement"), "bot_ready": s.get("bot_ready"),
            "map": s.get("map"), "constraints": s.get("constraints"),
            "wins_needed": s.get("wins_needed"),
            "maps": p.get("maps"), "excluded_maps": p.get("excluded_maps"),
            "categories": p.get("categories"), "minutes": p.get("minutes"),
            # tower XP follows invested cash: which towers this game levels up
            "cost_share": invested_cash(s),
        }))
    return specs


def _looks_like_map_name(text):
    """A plausible map title (letters, digits, spaces, ' # &), not OCR debris
    such as a medal count or a hero level."""
    import re
    t = text.strip()
    return len(re.sub(r"[^A-Za-z]", "", t)) >= 4 and re.fullmatch(r"[A-Za-z0-9 '#&.!-]+", t) is not None


class Bot:
    def __init__(self, account_path=None):
        import ctypes
        # ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED: no sleep, no screen-off
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000003)
        self.s = Screen()
        self.inp = Input(self.s)
        self.lay = L.get(self.s.width, self.s.height)
        self.account = AccountState.load(account_path or current_path())
        self.menus = Menus(self.s, self.inp)
        self.strats = load_all()
        self.failures = 0
        self.bad = set()        # (map, mode) that failed to start this session
        self._level_synced = False
        self.skip_known = None
        self._roster_done = False
        self._ach_at = _ach_last()  # every ACH_EVERY, remembered across restarts
        self.uid = None             # signed-in account, read from Settings
        self._games_since_id = 0
        self._mm_before = None
        self._games_since_mk = 99  # check Monkey Knowledge at session start, then every 3 games
        self._hero_failed = set()  # heroes the picker could not equip this session
        self._errors = _load_errors()  # error streak, survives restarts (see _game_error)
        self._medals_due = False   # sweep map medals at the next account check (account switched)

    # -- navigation ---------------------------------------------------------------
    def to_main_menu(self, tries=12):
        unknown_streak = 0
        for _ in range(tries):
            st = self.menus.identify()
            unknown_streak = unknown_streak + 1 if st == "unknown" else 0
            log.info("screen: %s", st)
            if st == "main_menu":
                return True
            if st == "pause":
                self.menus.click_word("home")
            elif st == "victory":
                self.menus.leave_victory()
            elif st == "defeat":
                self.menus.leave_defeat()
            elif st in ("map_select", "difficulty", "mode_select", "hero_select", "upgrade_tree",
                        "profile", "overwrite", "account", "monkeys_menu"):
                self.inp.click(0.044, 0.055)  # back arrow
                time.sleep(0.4)
            elif st == "level_up":
                self.menus.handle_level_up()
            elif st == "tower_choice":
                self._tower_choice()
            elif st == "title":
                if not self.menus.click_word("start"):
                    self.inp.click(0.5, 0.9)
                time.sleep(3.0)
            elif st == "in_game":
                self.inp.click(*self.lay["gear"])
                time.sleep(0.8)
            else:
                # transitions read as "unknown" for a moment: wait before acting,
                # and only fall back to the back arrow after repeated unknowns
                if not self.menus.dismiss_popup():
                    time.sleep(0.6)
                    if unknown_streak >= 3:
                        self.inp.click(0.044, 0.055)
                        time.sleep(1.0)
        return False

    def _tower_choice(self):
        name = self.menus.handle_tower_choice(tower_chooser(self.account))
        tid = T.find_tower(name) if name else None
        if tid:
            self.account.unlock_tower(tid)
            self.account.save()

    def read_level(self):
        """Player level from the star badge on the main menu."""
        from .hud import parse_int, rec_text
        from .vision import crop
        f = self.s.grab()
        lvl = parse_int(rec_text(crop(f, (0.095, 0.03, 0.125, 0.08)))[0])
        time.sleep(0.3)
        lvl2 = parse_int(rec_text(crop(self.s.grab(), (0.095, 0.03, 0.125, 0.08)))[0])
        # two agreeing reads; between games the level only rises a few steps, but
        # the first read of a session may adopt any save file's level
        cur = self.account.player_level
        plausible = cur <= lvl2 <= cur + 4 if self._level_synced else (lvl2 or 0) >= 1
        if lvl and lvl == lvl2 and not plausible and self._level_synced:
            log.warning("level reads %d but notes say %d - checking which account is signed in",
                        lvl, cur)
            self._check_account(force=True)
            return lvl
        if lvl and lvl == lvl2 and plausible:
            if lvl > cur + 4:
                log.warning("adopting save-file level %d (notes said %d)", lvl, cur)
            self._level_synced = True
            events = self.account.sync_level(lvl)
            for e in events:
                log.info(e)
            # tower choices are made on screen as they come up; don't queue them
            self.account.pending_tower_choices.clear()
            self.account.save()
        return lvl

    def open_map(self, map_name):
        """Main menu -> map select -> search -> map's difficulty screen."""
        set_state(f"opening map {map_name}")
        for attempt in range(4):
            self.inp.click(0.5, 0.88)  # PLAY
            st = self.menus.wait_for("map_select", timeout=5)
            if st == "map_select":
                break
            log.info("after PLAY: %s", st)
            if st != "main_menu":
                self.menus.dismiss_popup()
                self.to_main_menu()
        else:
            log.warning("open_map: PLAY did not reach map select")
            return False
        self.inp.click(0.044, 0.154)  # search (magnifier)
        time.sleep(0.5)
        self.inp.click(0.52, 0.04)    # focus the search box
        time.sleep(0.2)
        self.inp.type_text(map_name)
        target = norm(map_name)
        label = None
        end = time.time() + 5
        while label is None and time.time() < end:  # results filter in as you type
            time.sleep(0.3)
            for w in sorted(self.menus.read(), key=lambda w: (w.y, w.x)):
                if w.y < 0.1 or w.y > 0.9:
                    continue  # the search box itself / bottom buttons
                if target in norm(w.text) or norm(w.text) in target and len(norm(w.text)) > 4:
                    label = w
                    break
        if label is None:
            log.warning("open_map: no search result matching %r (saw %s)", map_name,
                        [w.text for w in self.menus.words][:12])
            return False
        self.sync_medals(map_name, label)
        if self.skip_known and self.skip_known(map_name):
            return "known"
        for _ in range(3):
            self.inp.click(label.x, min(0.95, label.y + 0.1))  # thumbnail sits under the name
            if self.menus.wait_for("difficulty", timeout=4) == "difficulty":
                return True
            if not self.menus.has("clicktounlock", "tounlock"):
                break
            log.info("unlocking map %s", map_name)  # first click unlocks a new map (free)
            time.sleep(1.5)
        log.warning("open_map: clicking %s did not open its difficulty screen (screen: %s, saw %s)",
                    map_name, self.menus.identify(), [w.text for w in self.menus.words][:12])
        return False

    # Map-select screen (calibrated 2026-10-21, 1920x1200): category tabs along
    # the bottom, page arrow on the right. Every category starts on a new page.
    CATEGORY_TABS = {"beginner": (0.282, 0.93), "intermediate": (0.427, 0.93),
                     "advanced": (0.573, 0.93), "expert": (0.719, 0.93)}
    NEXT_PAGE = (0.903, 0.40)

    def _page_names(self):
        """OCR the map-name labels on the current map-select page.
        Returns [(text, (col, row))] for words sitting on a card's name label."""
        from .medals import grid_cell
        out = []
        for w in self.menus.read():
            if not 0.1 < w.y < 0.75:
                continue
            cell = grid_cell(w.x, w.y)
            if cell is not None and len(w.text.strip()) >= 3:
                out.append((w.text.strip(), cell))
        return out

    def _match_map(self, text):
        """Known map for an OCR'd label, tolerating small misreads; else None."""
        import difflib
        from .account import MAPS, _norm
        key = _norm(text)
        names = {_norm(m): m for m in MAPS}
        if key in names:
            return names[key]
        close = difflib.get_close_matches(key, names, n=1, cutoff=0.8) if len(key) >= 5 else []
        return names[close[0]] if close else None

    def _read_category_tabs(self):
        """On the map-select screen: click each category tab, read its first
        page and its unlock bar. Stores account.category_progress and
        returns {category: normalised names on its first page} (empty for a
        tab whose page could not be told apart, see tab_first_pages)."""
        import re
        from .account import _norm
        reads = {}
        for cat, pos in self.CATEGORY_TABS.items():
            self.inp.click(*pos)
            time.sleep(0.8)
            reads[cat] = {_norm(t) for t, _ in self._page_names()}
            # A locked category shows its unlock bar at the top ("7 / 12" map wins) ...
            bar = next((re.search(r"(\d+)\s*/\s*(\d+)", w.text) for w in self.menus.words
                        if w.y < 0.08 and re.search(r"\d+\s*/\s*\d+", w.text)), None)
            # ... or, on Expert, a banner: "Beat 13 more maps to unlock all Expert maps"
            more = next((re.search(r"beat\s*(\d+)\s*more", w.text, re.I) for w in self.menus.words
                         if re.search(r"beat\s*\d+\s*more", w.text, re.I)), None)
            if bar and int(bar.group(1)) < int(bar.group(2)):
                self.account.category_progress[cat] = [int(bar.group(1)), int(bar.group(2))]
                log.info("medal scan: %s maps locked (%s/%s map wins)", cat, bar.group(1), bar.group(2))
            elif more:
                self.account.category_progress[cat] = [0, int(more.group(1))]
                log.info("medal scan: %s maps locked (%s more wins needed)", cat, more.group(1))
            else:
                self.account.category_progress[cat] = [1, 1]  # no bar: unlocked
        first = tab_first_pages(reads)
        unclear = [cat for cat in reads if reads[cat] and not first[cat]]
        if unclear:
            log.warning("medal scan: tabs %s showed the same page - not using them to tell categories", unclear)
        return first

    def scan_all_medals(self, max_pages=30):
        """Read every map card on the map-select pages (~30 s for ~90 maps):
          * adopt each mode's medal shown on the card (a save made elsewhere
            has medals our notes never saw), and
          * register maps the code does not know yet (new game updates), under
            the category tab they are listed in.
        Returns the number of maps read."""
        from . import mapgeom
        from .account import MAPS, _norm, canonical_map, register_map
        from .medals import read_grid_card
        set_state("reading map medals from the map select pages")
        self.inp.click(0.5, 0.88)  # PLAY
        if self.menus.wait_for("map_select", timeout=6) != "map_select":
            log.warning("medal scan: PLAY did not reach map select")
            self.to_main_menu()
            return 0
        # first page of each category tab -> lets us tell which category a
        # page belongs to while paging through everything below
        first_page = self._read_category_tabs()
        self.inp.click(*self.CATEGORY_TABS["beginner"])
        time.sleep(0.8)

        # A map belongs to the category of the page it is read on. Pages are
        # told apart by the game's own map data first and by an unambiguous
        # tab match second (page_category); until either says, no category is
        # recorded at all.
        category = None
        seen_pages, found, new_medals, new_maps = [], {}, 0, []
        for _ in range(max_pages):
            time.sleep(0.5)
            frame = self.s.grab()
            labels = [(text, cell, self._match_map(text)) for text, cell in self._page_names()]
            category = page_category({_norm(t) for t, _, _ in labels}, [n for _, _, n in labels if n],
                                     first_page, category, MAPS)
            page = []
            for text, cell, name in labels:
                if name is None and category and _looks_like_map_name(text) and mapgeom.unknown_map_id(text):
                    # a card for a map bundle the game has and our list lacks
                    name = text.strip().title()
                    if register_map(name, category):
                        new_maps.append(f"{name} ({category})")
                if name is None or name in page:
                    continue
                page.append(name)
                if category and not self.account.note_map_category(name, category):
                    log.warning("medal scan: %s read on a %s page, but the game data lists it as %s",
                                name, category, self.account.map_category(name))
                found[name] = read_grid_card(frame, *cell)
            if not page or page in seen_pages:
                break  # wrapped around to a page we already read
            seen_pages.append(page)
            self.inp.click(*self.NEXT_PAGE)
        # The cards are the truth: set every mode exactly as shown (adds medals
        # earned elsewhere and drops ones our notes got wrong).
        dropped_medals = []
        for name, medals in found.items():
            rec = self.account.medals.setdefault(canonical_map(name), {})
            for mode, earned in medals.items():
                if earned and not rec.get(mode):
                    new_medals += 1
                elif rec.get(mode) and not earned:
                    dropped_medals.append(f"{name} {mode}")
                rec[mode] = bool(earned)
        if dropped_medals:
            log.warning("medal scan: removed medals the game does not show: %s", ", ".join(dropped_medals))
        odd = self.account.out_of_chain_medals()
        if odd:   # kept: earned in someone else's co-op lobby (see AccountState.out_of_chain_medals)
            log.info("%d medals earned outside the unlock chain (co-op): %s", len(odd), odd[:8])
        self.account.save()
        log.info("medal scan: %d maps read on %d pages, %d medals adopted", len(found), len(seen_pages), new_medals)
        if new_maps:
            log.warning("new maps found and added: %s", ", ".join(new_maps))
        self.to_main_menu()
        return len(found)

    def _refresh_map_geometry(self):
        """Read maps that are new or changed in the game files (a game update
        adds or rebuilds map bundles). Takes ~15 s the first time, ~1 s after."""
        try:
            from . import gamedata, gamefiles
            gamefiles.refresh(status=set_state)
            gamedata.refresh()   # round sets and achievements
        except Exception:  # never let this stop the bot: learning still works
            log.exception("reading map geometry from the game files failed")

    def _use_geometry(self, model, map_name, reverse=False):
        """Fill the model from the game's own map files when they are available
        (exact track, progress, placement and sight blockers - no learning).
        Re-applied when the game updates the map or the scan was dropped.
        Returns True when the model now holds game geometry."""
        from . import mapgeom
        from .tracklearn import LEARNED_ROUNDS
        geom = mapgeom.load(map_name)
        if geom is None:
            return False
        # the stamp names the game bundle AND our extraction version, so both a
        # game update and an improved extractor re-apply the geometry
        stamp = f'{geom.get("bundle")}#v{geom.get("version")}'
        if model.geometry_bundle == stamp and model.scanned("land"):
            return True
        mapgeom.apply(model, geom)
        if reverse:  # Reverse runs the same track backwards
            model.t_sum = np.where(model.t_cnt > 0, model.t_cnt - model.t_sum, 0).astype(np.float32)
        model.geometry_bundle = stamp
        model.rounds_traced = max(model.rounds_traced, LEARNED_ROUNDS)  # no noisy in-game tracing
        model.save()
        return True

    def _learn_track_if_needed(self, map_name):
        """First visit (or a model learned the old, noisy way): trace the
        track in Sandbox before playing for real."""
        from . import mapgeom
        from .tracklearn import learn_track, needs_sandbox, sandbox_difficulty
        if mapgeom.load(map_name) is not None:
            return  # the game's own map files describe this map exactly
        if not needs_sandbox(MapModel.load(map_name, self.lay["playfield"])):
            return
        if sandbox_difficulty(self.account, map_name) is None:
            return  # Sandbox still locked on this map: the in-game tracer has to do
        try:
            learn_track(self, map_name)
        except (FocusLost, Aborted):
            raise
        except Exception:
            log.exception("sandbox track learning failed - playing with the old model")
        self.to_main_menu()

    def sync_medals(self, map_name, label):
        """Adopt the medals the save file shows on this map's card."""
        from .account import canonical_map
        from .medals import read_card
        seen = read_card(self.s.grab(), label.x, label.y)
        # The search card's slots are unreliable (they invented a Hard medal on
        # Luminous Cove and Impoppable ones): log only. The map-select sweep
        # (scan_all_medals, daily per account) sets medals from the cards.
        if any(seen.values()):
            log.info("search card for %s suggests %s (not adopted)", map_name,
                     [d for d, e in seen.items() if e])
        seen = {}
        rec = self.account.medals.setdefault(canonical_map(map_name), {})
        new = [d for d, earned in seen.items() if earned and not rec.get(d)]
        for d in new:
            rec[d] = True
        if new:
            log.info("save file shows medals on %s not in our notes: %s", map_name, new)
            self.account.save()

    def start(self, plan):
        # a first-time medal that the card shows as already earned: replan
        self.skip_known = (lambda m: plan.first_time and self.account.has_medal(m, plan.mode_key))
        opened = self.open_map(plan.map)
        if opened == "known":
            log.info("%s %s already earned on this save - replanning", plan.map, plan.mode_key)
            self.to_main_menu()
            return "known"
        if not opened:
            log.error("could not open map %s", plan.map)
            return False
        # clicks made during a screen transition are dropped: retry each step
        for _ in range(3):
            self.menus.read()
            if self.menus.click_word(plan.difficulty, dy=-0.09, region=(0, 0.3, 1, 0.7)) and                     self.menus.wait_for("mode_select", timeout=3) == "mode_select":
                break
        else:
            log.warning("start: difficulty %s did not open its modes", plan.difficulty)
            return False
        for _ in range(3):
            words = self.menus.read()
            clicked = self.menus.click_word(MODE_BUTTON_TEXT.get(plan.mode, plan.mode), dy=-0.08)
            if not clicked and plan.mode in MODE_BUTTON_POS:
                x, y = MODE_BUTTON_POS[plan.mode]
                # the label sits under the icon: never click a slot labelled Sandbox
                near = [w for w in words if abs(w.x - x) < 0.09 and 0.03 < w.y - y < 0.14]
                if any("sandbox" in norm(w.text) for w in near):
                    log.warning("start: %s slot shows Sandbox - not clicking", plan.mode)
                    return False
                log.info("click mode %s at its slot (label %s)", plan.mode, [w.text for w in near][:2])
                self.inp.click(x, y)
                clicked = True
            if clicked:
                if self.menus.wait_for({"in_game", "overwrite", "unknown"}, timeout=3) != "mode_select":
                    break
        else:
            log.warning("start: mode %s did not start", plan.mode)
            return False
        end = time.time() + 30  # loading, overwrite prompt, mode intro popups
        while time.time() < end:
            st = self.menus.wait_for({"in_game", "overwrite"}, timeout=3)
            if st == "in_game":
                return True
            if st == "overwrite":
                self.menus.click_word("ok", "yes", "overwrite")
            elif st == "unknown":
                self.menus.dismiss_popup()
        return self.menus.in_game()

    # -- one game ------------------------------------------------------------------
    def play(self, plan):
        strat = self.strats[plan.strategy_id]
        ok, why = usable(strat, plan.mode_key, self.account, map_name=plan.map,
                         allow_achievement=bool(strat.get("achievement")))
        if not ok:
            raise RuntimeError(f"{plan.strategy_id} not usable for {plan.map} {plan.mode_key}: {why}")
        diff = {"easy": "easy", "medium": "medium", "hard": "hard"}.get(plan.difficulty, "hard")
        if plan.mode_key in ("impoppable", "chimps"):
            diff = "impoppable"
        # the hero was equipped from the main menu (equip_hero_for); the game
        # reads the equipped hero's name again when it is placed
        hero = self.account_selected_hero()
        g = Game(self.s, self.inp, self.lay, difficulty=diff, hero=hero)
        self.menus.g = g
        # probe which towers the hotkeys can pick up, once per session
        # (later unlocks are seen on the level-up screen). Only towers the
        # account is not known to own, and that this mode lets us place
        # (Primary Only etc.), are worth a press: probing every tower took
        # ~17 s per session and 80 s in Primary Only.
        if self._roster_done:
            roster = {}
        else:
            from .strategy import MODE_TOWER_FILTER
            only = MODE_TOWER_FILTER.get(plan.mode_key)
            unknown = [k for k, t in T.TOWERS.items()
                       if k not in self.account.unlocked_towers and only in (None, t["category"])]
            roster = g.probe_roster(unknown) if unknown else {}
        self._roster_done = True
        # The probe only ADDS towers. Ownership is read in the Monkeys menu
        # (xpspend.sync_all); a probe can fail wholesale (a popup, a slow
        # load) and once removed every tower, leaving a hero alone to lose.
        if roster and not any(roster.values()):
            log.warning("roster probe found no tower at all - ignoring it")
        for kind, ok in roster.items():
            if ok:
                self.account.unlocked_towers.add(kind)
        self.account.save()
        from .strategy import rules
        # Reverse runs the same track backwards: its progress map is mirrored
        key = plan.map + (" reverse" if rules(plan.mode_key).get("reversed") else "")
        model = MapModel.load(key, self.lay["playfield"])
        if not self._use_geometry(model, plan.map, reverse=key != plan.map) and key != plan.map:
            base = MapModel.load(plan.map, self.lay["playfield"])
            if not model.scanned("land"):
                model.scan = dict(base.scan)  # placement is identical
            if base.sandbox_rounds and not model.sandbox_rounds:
                from .tracklearn import reversed_from
                reversed_from(base, model)
        if not model.scanned("land"):
            log.info("first visit to %s: scanning placement", plan.map)
            set_state("first visit: scanning where towers can be placed")
            scan_placement(g, model, "dart", "land")
            model.save()
        # water towers in this plan: find the water once (cheap, land-blocked cells only)
        steps = strat.get("plan", []) + strat.get("fill", [])
        kinds = {st.get("kind") for st in steps} | set((strat.get("planner") or {}).get("towers") or {})
        water = sorted(k for k in kinds if k in T.TOWERS
                       and T.TOWERS[k]["placement"] in ("water", "land_or_water"))
        if T.HEROES.get(hero, {}).get("placement") in ("water", "land_or_water"):
            water.append("hero")
        if water and (not model.water_scanned() or model.water_pending() > 3):
            log.info("scanning water on %s for %s", plan.map, water)
            scan_water(g, model, "sub" if "sub" in water else ("hero" if water == ["hero"] else water[0]))
            model.save()
        ex = Executor(g, model, strat, plan.mode_key, self.account)
        g.on_hero = lambda hid: setattr(self.account, "selected_hero", hid)
        res = Match(g, self.menus, model, ex, self.account,
                    on_tower_choice=tower_chooser(self.account)).play()
        won = res.get("outcome") == "victory"
        # towers that played earned XP: their "can't afford" notes are stale
        forget_short(self.account, {p.kind for p in g.towers.values()} | strategy_towers(strat))
        # a game not won may have ended for a reason outside the map: look at
        # the screen before leaving it (see outside_cause)
        screen = None if won else self.menus.identify()
        cause = None if won else outside_cause(res.get("outcome"), screen)
        if screen in ("title", "account"):
            self._games_since_id = ID_CHECK_EVERY  # read the User ID before the next game
        if won:
            self.menus.leave_victory()
        else:
            self.menus.leave_defeat()
        # the Monkey Money total on the main menu, before vs after, is the game's real reward
        mm_after = self.read_mm()
        mm = None
        if self._mm_before is not None and mm_after is not None and 0 <= mm_after - self._mm_before < 5000:
            mm = mm_after - self._mm_before
        res["mm"] = mm
        # Note: Monkey Money gained is NOT proof of a win (level-up rewards pay
        # too: an abandoned Tree Stump game "paid" 200). The medal sweep, which
        # reads every map card daily, is what settles medals.
        if cause:
            # not a loss of this map or strategy: no stats, and run() does not bench it
            res["outside_cause"] = cause
            log.warning("%s %s ended early: %s - not recorded as a loss", plan.map, plan.mode_key, cause)
        else:
            self.account.record_result(plan.map, plan.mode_key, plan.strategy_id, won,
                                       round_reached=res.get("round"), minutes=res.get("minutes"),
                                       mm_gained=mm, hero=hero)
        self.account.save()
        return res

    def read_mm(self):
        """Monkey Money on the main menu (two agreeing reads), else None."""
        if self.menus.identify() != "main_menu":
            return None
        from .hud import parse_int, rec_text
        from .vision import crop
        reads = []
        for _ in range(2):
            reads.append(parse_int(rec_text(crop(self.s.grab(), (0.895, 0.025, 0.955, 0.09)))[0]))
            time.sleep(0.2)
        if reads[0] is not None and reads[0] == reads[1]:
            self.account.monkey_money = reads[0]
            return reads[0]
        return None

    def run(self, hours=8.0):
        end = time.time() + hours * 3600
        code_stamp = _code_stamp()
        self._refresh_map_geometry()
        progress.write(self.account, "starting")
        while time.time() < end:
            plan = None
            if PAUSE_FILE.exists():
                self.pause_at_menu()
                continue
            if _code_stamp() != code_stamp:
                # between games: exit so the supervisor restarts us on the new code,
                # but only if it imports cleanly (a half-saved edit must not kill us)
                if _code_imports():
                    log.warning("code or strategies changed - exiting to reload")
                    raise SystemExit(4)
                log.error("changed code does not import - staying on the running version")
                code_stamp = _code_stamp()
            if not self.wait_until_offline():
                continue
            if self.failures >= 8:
                log.error("too many consecutive failures; stopping")
                return
            try:
                self.s.focus()
                if not self.to_main_menu():
                    log.error("cannot reach main menu")
                    self.failures += 1
                    time.sleep(5)
                    continue
                self._check_account()
                self.read_level()
                # which heroes the account owns, from the HEROES screen (weekly)
                try:
                    from .heroes import HeroPicker
                    set_state("checking which heroes the account owns")
                    HeroPicker(self.s, self.inp, self.menus, self.account).scan_owned_if_due()
                except (FocusLost, Aborted):
                    raise
                except Exception:
                    log.exception("hero scan failed")
                    self.to_main_menu()
                # Monkey Knowledge: once per session, then only when the game
                # puts its "!" badge on the Knowledge button (new points)
                from .mk import KNOWLEDGE_BUTTON
                mk_due = self._games_since_mk >= 99 or self.menus.has_badge(*KNOWLEDGE_BUTTON)
                if self.account.player_level >= 30 and mk_due:
                    self._games_since_mk = 0
                    try:  # spend new Monkey Knowledge points (MM / XP boosts first)
                        set_state("spending Monkey Knowledge points")
                        got = Knowledge(self.s, self.inp, self.menus, self.account).spend()
                        if got:
                            log.info("Monkey Knowledge: %s", got)
                    except (FocusLost, Aborted):
                        raise
                    except Exception:
                        log.exception("Monkey Knowledge spending failed")
                    self.to_main_menu()
                # Achievements: claim when the ribbon shows its "!" badge; the
                # full progress scan the planner uses runs at most daily
                self._achievements_if_due()
                plan = self.next_plan()
                if plan is None:
                    log.error("planner has nothing to play - waiting 30 min (benches expire, XP grows)")
                    self._idle(1800, "idle: nothing to play", code_stamp)
                    continue
                log.info("NEXT: %s", plan.reason)
                set_state(f"opening {plan.map} {plan.mode_key}", game=f"{plan.map} {plan.mode_key}")
                self._mm_before = self.read_mm()
                try:  # spend tower XP on this plan's upgrades before it needs them
                    set_state("unlocking upgrades with tower XP")
                    got = unlock_for_strategy(self.s, self.inp, self.menus, self.account,
                                              self.strats[plan.strategy_id])
                    if got:
                        log.info("unlocked before the game: %s", got)
                except (FocusLost, Aborted):
                    raise
                except Exception:
                    log.exception("XP spending failed - continuing")
                    self.to_main_menu()
                self._learn_track_if_needed(plan.map)
                self.equip_hero_for(plan)
                started = self.start(plan)
                if started == "known":
                    continue
                if not started:
                    log.error("failed to start %s %s - skipping it this session",
                              plan.map, plan.mode_key)
                    self.bench(plan.map, plan.mode_key, hours=2, why="failed to start")
                    self.failures += 1
                    continue
                # the plan's towers earn XP from here on (even if the game breaks)
                forget_short(self.account, strategy_towers(self.strats[plan.strategy_id]))
                res = self.play(plan)
                self._games_since_id += 1
                self._games_since_mk += 1
                if res.get("outcome") != "victory" and not res.get("outside_cause"):
                    self.bench(plan.map, plan.mode_key, hours=12, why=res.get("outcome", "loss"))
                log.info("RESULT %s", res)
                self._game_done(plan)
                progress.record_result(plan, res)
                progress.write(self.account, "game finished")
                self.failures = 0
            except Aborted:
                raise
            except GameNotFound:
                self.relaunch_game()
            except FocusLost as e:
                log.warning("%s - waiting for the game to be in front again", e)
                time.sleep(10)
            except Exception as e:
                log.exception("game loop error - recovering to main menu")
                self.failures += 1
                # bench only a map/mode that fails twice; wait instead when the
                # same error repeats game after game (a bot bug, not a bad map)
                self._game_error(e, plan, code_stamp)

    def _check_account(self, force=False):
        """Read the signed-in account's User ID; switch state files if it changed,
        and fully re-sync an account that is new or not synced for a day."""
        if not force and self._games_since_id < ID_CHECK_EVERY and self.uid:
            return
        self._games_since_id = 0
        uid = read_user_id(self.s, self.inp, self.menus)
        if not uid:
            log.warning("could not read the account's User ID")
            return
        if uid != self.uid:
            previous = self.uid or current_path().stem  # after a restart: the last run's account
            if previous != uid:
                log.warning("account changed: %s -> %s", previous, uid)
                self._medals_due = True  # another save: its medals may differ from our notes
            self.account, is_new = load_for(uid)
            self.uid = uid
            self._level_synced = False
            self._roster_done = False  # re-probe towers in the next game
            if is_new:
                self._ach_at = 0.0  # scan achievements right away
        if is_stale(uid):
            log.info("syncing account %s from the game (upgrades, level)", uid)
            set_state("reading the account: owned towers and upgrade trees")
            sync_all(self.s, self.inp, self.menus, self.account)
            self.to_main_menu()
            mark_synced(uid)
        if self._medals_due or _medal_sweep_due(uid):
            # ~40 s: every map's medals (and any new maps) at once. It used to
            # run at every process start - 14 sweeps in one night of code
            # reloads (2026-10-21/22), 13 of them adopting 0 medals. Our own
            # wins are recorded as they happen, so a daily sweep (or one after
            # an account switch) is enough; it stays authoritative when it runs.
            if self.scan_all_medals():
                _write_stamp(_medal_sweep_file(uid), time.time())
                self._medals_due = False
            self.to_main_menu()

    # -- benches: (map, mode) that just lost or broke are not retried for a while
    def _bench_file(self):
        return ROOT_DIR / "data" / "accounts" / f"{self.uid or 'default'}.bench.json"

    def _benches(self):
        import json
        try:
            d = json.loads(self._bench_file().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            d = {}
        now = time.time()
        return {k: v for k, v in d.items() if v > now}

    def bench(self, map_name, mode, hours, why=""):
        import json
        d = self._benches()
        d[f"{map_name}|{mode}"] = time.time() + hours * 3600
        try:
            self._bench_file().parent.mkdir(parents=True, exist_ok=True)
            self._bench_file().write_text(json.dumps(d), encoding="utf-8")
        except OSError:
            pass
        log.warning("benched %s %s for %gh (%s)", map_name, mode, hours, why)

    def benched(self, map_name, mode):
        return f"{map_name}|{mode}" in self._benches() or (map_name, mode) in self.bad

    def account_selected_hero(self):
        return getattr(self.account, "selected_hero", None) or "quincy"

    def equip_hero_for(self, plan):
        """Before opening the map: equip the hero the plan's strategy wants
        (strategy.hero_for: its own hero if owned, else the best owned one its
        constraints allow). Nothing happens when it is already equipped."""
        hero = hero_for(self.strats[plan.strategy_id], self.account)
        if not hero or hero == getattr(self.account, "selected_hero", None):
            return
        if hero in self._hero_failed:
            return   # the picker could not find it this session; don't retry every game
        if not self.select_hero(hero):
            self._hero_failed.add(hero)

    def select_hero(self, hero):
        """Equip `hero` in the HEROES menu of the main menu (heroes.HeroPicker:
        clicks the portraits and reads the name each one shows) and record it
        as account.selected_hero. True when it is equipped."""
        from .heroes import HeroPicker
        set_state(f"equipping hero {hero}")
        try:
            ok = HeroPicker(self.s, self.inp, self.menus, self.account).select(hero)
        except (FocusLost, Aborted):
            raise
        except Exception:
            log.exception("hero selection failed")
            ok = False
        if not ok:
            log.warning("could not equip %s - keeping %s", hero, self.account_selected_hero())
        self.to_main_menu()
        return ok

    def wait_until_offline(self, poll=30):
        """The bot only plays while the game is offline (dummy account rule).
        Returns True when it may play; otherwise parks at the main menu, says
        why in the status line, waits `poll` seconds and returns False."""
        from . import offline
        ok, reason = offline.check()
        if ok:
            if getattr(self, "_online_reason", None):
                log.warning("%s - resuming", reason)
                self._online_reason = None
            return True
        if reason != getattr(self, "_online_reason", None):
            log.error("%s - not playing until the game is offline "
                      "(block BloonsTD6.exe in Windows Firewall; see README)", reason)
            self._online_reason = reason
            self.to_main_menu()
        set_state(f"waiting: {reason}")
        progress.write(self.account, f"waiting: {reason}")
        end = time.time() + poll
        while time.time() < end and not PAUSE_FILE.exists():
            time.sleep(2)
        return False

    def pause_at_menu(self):
        """Park at the main menu while the PAUSE file exists (between games only),
        so a developer can use the game safely."""
        self.to_main_menu()
        log.warning("PAUSE file present - idling at the main menu")
        set_state("paused")
        # Refresh the status now and then: without it the watchdog killed the
        # parked bot every ~11 minutes (log 2026-10-22: restarts at 02:47,
        # 02:58, 03:09, 03:21), and each restart clicked back to the main
        # menu - under the developer's mouse.
        shown = time.time()
        while PAUSE_FILE.exists():
            time.sleep(3)
            if time.time() - shown > IDLE_STATUS_EVERY:
                set_state("paused")
                shown = time.time()
        log.warning("PAUSE file removed - resuming")
        set_state("resuming")

    def _idle(self, seconds, why, code_stamp=None):
        """Wait up to `seconds` without looking hung: the supervisor's watchdog
        kills a bot whose log and status file stay unchanged for 10 minutes,
        and a single 30-minute time.sleep() did exactly that. The status is
        refreshed every IDLE_STATUS_EVERY s. Ends early when the PAUSE file
        appears or the code changes, so a fix loads at once."""
        end = time.time() + seconds
        next_status = 0.0
        while time.time() < end:
            if PAUSE_FILE.exists() or (code_stamp is not None and _code_stamp() != code_stamp):
                return
            if time.time() >= next_status:
                set_state(f"{why} ({(end - time.time()) / 60:.0f} min left)")
                next_status = time.time() + IDLE_STATUS_EVERY
            time.sleep(min(IDLE_POLL, max(0.0, end - time.time())))

    def _achievements_if_due(self):
        """Claim achievement rewards when the ribbon shows its "!" badge, and
        read every card's progress (which the planner uses) at most once per
        ACH_EVERY. The badge used to start that full scan: 204 s and 192 s
        only 28 minutes apart (log 2026-10-22 02:02 and 02:30); a claim pass
        reads one or two pages (Achievements.claim).
        If the badge is still lit after a claim pass, the full scan runs at
        once; if even that leaves it lit, the badge means something the bot
        cannot act on, and it is ignored until the next daily scan - so it
        can never start a scan before every game."""
        from .achievements import BADGE
        full = time.time() - self._ach_at > ACH_EVERY
        badge = (not full and _read_stamp(ACH_MUTE) < self._ach_at
                 and self.menus.has_badge(*BADGE))
        if not (full or badge):
            return
        ach = Achievements(self.s, self.inp, self.menus)
        try:
            if badge:
                set_state("claiming achievement rewards")
                ach.claim()
                time.sleep(1.0)  # let the main menu redraw the ribbon before judging its badge
                full = self.menus.has_badge(*BADGE)
                if full:
                    log.warning("achievements badge still lit after claiming - reading the whole list")
            if full:
                self._ach_at = time.time()
                _ach_mark(self._ach_at)
                set_state("scanning achievements, claiming rewards")
                ach.scan(collect=True)
                if self.menus.has_badge(*BADGE):
                    log.warning("achievements badge still lit after a full scan - ignoring it until the next one")
                    _write_stamp(ACH_MUTE, self._ach_at)
        except (FocusLost, Aborted):
            raise
        except Exception:
            log.exception("achievements failed")
        self.to_main_menu()

    def _game_error(self, e, plan, code_stamp=None):
        """After a game-loop error: bench the map only when the same map and
        mode failed twice, and stop benching altogether when the same error
        hits game after game - that is a bug in the bot, not a bad map (log
        2026-10-22 02:04-02:15: one setup bug benched 13 maps for 6 h each).
        The counts are kept on disk, so a restart does not reset them."""
        errors = self._errors
        sig = _error_signature(e)
        errors["streak"] = errors["streak"] + 1 if sig == errors["sig"] else 1
        errors["sig"] = sig
        key = f"{plan.map}|{plan.mode_key}" if plan is not None else None
        if key:
            errors["maps"][key] = errors["maps"].get(key, 0) + 1
        _save_errors(errors)
        if errors["streak"] >= ERROR_STREAK_WAIT:
            log.error("the same error in %d games in a row (%s: %s) - not benching maps; "
                      "waiting 10 min for a code fix", errors["streak"], sig, e)
            self._idle(600, f"error loop: {sig}: {str(e)[:80]}", code_stamp)
        elif key and errors["maps"][key] >= ERROR_BENCH_AFTER:
            self.bench(plan.map, plan.mode_key, hours=6, why=f"error twice: {sig}")
            errors["maps"].pop(key)
            _save_errors(errors)
        elif key:
            log.warning("%s %s failed (%s) - it is benched only if it fails again", plan.map, plan.mode_key, sig)

    def _game_done(self, plan):
        """A game ran to its end: the error streak and this map's count reset."""
        self._errors["sig"], self._errors["streak"] = None, 0
        self._errors["maps"].pop(f"{plan.map}|{plan.mode_key}", None)
        _save_errors(self._errors)

    def relaunch_game(self, wait=90):
        """BTD6 closed or crashed: start it again through Steam and reattach."""
        import os
        log.error("BTD6 window not found - relaunching through Steam")
        os.startfile("steam://rungameid/960090")
        t = time.time()
        while time.time() - t < wait:
            time.sleep(5)
            try:
                self.s.refresh()
                time.sleep(20)  # let the title screen finish loading
                self.s.refresh()
                log.info("BTD6 is back (%dx%d)", self.s.width, self.s.height)
                for _ in range(6):  # title screen: click through to the main menu
                    if self.menus.identify() == "main_menu":
                        break
                    self.inp.click(0.5, 0.6)
                    time.sleep(3)
                return True
            except GameNotFound:
                continue
        return False

    def next_plan(self):
        """Best plan whose (map, mode) has not failed to start this session."""
        from .planner import GamePlan, rank_games
        from .account import MODES
        specs = planner_specs(self.strats, self.account)
        phase, reasons, cands = rank_games(self.account, specs)
        for c in cands:
            if self.benched(c.map, c.mode):
                continue
            from .planner import next_game  # noqa: F401  (same scoring as next_game)
            mi = MODES[c.mode]
            hero = (c.s.heroes or (None,))[0]
            return GamePlan(
                map=c.map, difficulty=mi.difficulty, mode=mi.ui_mode, mode_key=c.mode,
                strategy_id=c.s.id, hero=hero,
                reason=f"[{phase}] {c.map} / {c.mode} with {c.s.id}: score {c.score:,.0f}/min; "
                       + ", ".join(c.notes),
                reasons=reasons, phase=phase, p_win=round(c.p, 3),
                expected_minutes=round(c.minutes, 1), expected_xp=0, expected_mm=0,
                score=round(c.score, 1), first_time=c.first)
        # Nothing to play (run() then idles): say why. The planner only offers
        # first-time medals that clear their win-chance bar; its first reason
        # line explains an empty list.
        log.warning("%s", "nothing to play right now: every winnable first-time medal is "
                          "benched after a recent loss or error" if cands else reasons[0])
        return None
