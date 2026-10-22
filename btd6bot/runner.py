"""Top level: pick the next game, navigate to it, play it, record it, repeat."""
import logging
import time

import numpy as np

from . import layout as L
from . import progress
from . import towers as T
from .account import AccountState
from .achievements import Achievements
from .xpspend import sync_all, unlock_for_strategy
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
from .strategy import Executor, coverage, hero_for, load_all, usable
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


def _ach_last():
    try:
        return float(ACH_STAMP.read_text().strip())
    except (OSError, ValueError):
        return 0.0


def _ach_mark(t):
    try:
        ACH_STAMP.write_text(str(t))
    except OSError:
        pass


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
        # page belongs to while paging through everything below. A locked
        # category also shows its unlock bar at the top ("7 / 12" map wins).
        import re
        first_page = {}
        for cat, pos in self.CATEGORY_TABS.items():
            self.inp.click(*pos)
            time.sleep(0.8)
            first_page[cat] = {_norm(t) for t, _ in self._page_names()}
            bar = next((re.search(r"(\d+)\s*/\s*(\d+)", w.text) for w in self.menus.words
                        if w.y < 0.08 and re.search(r"\d+\s*/\s*\d+", w.text)), None)
            # Expert shows a banner instead: "Beat 13 more maps to unlock all Expert maps"
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
        self.inp.click(*self.CATEGORY_TABS["beginner"])
        time.sleep(0.8)

        category = "beginner"
        seen_pages, found, new_medals, new_maps = [], {}, 0, []
        for _ in range(max_pages):
            time.sleep(0.5)
            frame = self.s.grab()
            labels = self._page_names()
            keys = {_norm(t) for t, _ in labels}
            for cat, first in first_page.items():
                if first and len(keys & first) >= 2:
                    category = cat
            page = []
            for text, cell in labels:
                name = self._match_map(text)
                if name is None and _looks_like_map_name(text) and mapgeom.unknown_map_id(text):
                    # a card for a map bundle the game has and our list lacks
                    name = text.strip().title()
                    if register_map(name, category):
                        new_maps.append(f"{name} ({category})")
                if name is None or name in page:
                    continue
                page.append(name)
                if MAPS.get(name) != category:  # the game lists it elsewhere
                    self.account.map_category_overrides[name] = category
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
        dropped = self.account.drop_impossible_medals()
        if dropped:
            log.warning("removed %d impossible medals (prerequisite not earned): %s", len(dropped), dropped[:8])
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
        # (scan_all_medals, once per session) sets medals from the cards.
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
            self.account.drop_impossible_medals()
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
        from .strategy import hero_for
        hero = hero_for(strat, self.account)
        if hero != self.account_selected_hero():
            self.select_hero(hero)
        hero = self.account_selected_hero()  # what is actually equipped
        g = Game(self.s, self.inp, self.lay, difficulty=diff, hero=hero)
        self.menus.g = g
        # probe which towers the hotkeys can pick up, once per session
        # (later unlocks are seen on the level-up screen)
        roster = {} if self._roster_done else g.probe_roster()
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
        # reads every map card each session, is what settles medals.
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
                from .achievements import BADGE as ACH_RIBBON
                if time.time() - self._ach_at > ACH_EVERY or self.menus.has_badge(*ACH_RIBBON):
                    self._ach_at = time.time()
                    _ach_mark(self._ach_at)
                    try:  # claim finished achievements' rewards, refresh progress
                        set_state("scanning achievements, claiming rewards")
                        Achievements(self.s, self.inp, self.menus).scan(collect=True)
                    except (FocusLost, Aborted):
                        raise
                    except Exception:
                        log.exception("achievements scan failed")
                    self.to_main_menu()
                plan = self.next_plan()
                if plan is None:
                    log.error("planner has nothing to play - waiting 30 min (benches expire, XP grows)")
                    set_state("idle: nothing to play")
                    time.sleep(1800)
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
                started = self.start(plan)
                if started == "known":
                    continue
                if not started:
                    log.error("failed to start %s %s - skipping it this session",
                              plan.map, plan.mode_key)
                    self.bench(plan.map, plan.mode_key, hours=2, why="failed to start")
                    self.failures += 1
                    continue
                res = self.play(plan)
                self._games_since_id += 1
                self._games_since_mk += 1
                if res.get("outcome") != "victory":
                    self.bench(plan.map, plan.mode_key, hours=12, why=res.get("outcome", "loss"))
                log.info("RESULT %s", res)
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
            except Exception:
                log.exception("game loop error - recovering to main menu")
                self.failures += 1
                if plan is not None:
                    self.bench(plan.map, plan.mode_key, hours=6, why="error")

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
            if self.uid:
                log.warning("account changed: %s -> %s", self.uid, uid)
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
        if getattr(self, "_medals_swept", None) != uid:
            # ~30 s once per session: every map's medals (and any new maps) at
            # once, instead of discovering earned medals one map search at a time
            self.scan_all_medals()
            self._medals_swept = uid
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

    def select_hero(self, hero):
        """Hero choice happens on the map/difficulty screen ('Change Hero'),
        which we pass through right before the game. Until the hero menu has
        been calibrated live this only records the wish and keeps the current
        hero, so the game always matches what Game() is told."""
        log.info("strategy prefers %s; hero switching not calibrated yet - keeping %s",
                 hero, self.account_selected_hero())

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
        while PAUSE_FILE.exists():
            time.sleep(3)
        log.warning("PAUSE file removed - resuming")
        set_state("resuming")

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
        return None
