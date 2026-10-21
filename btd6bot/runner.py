"""Top level: pick the next game, navigate to it, play it, record it, repeat."""
import logging
import time

from . import layout as L
from . import towers as T
from .account import AccountState
from .choices import tower_chooser
from .game import Game
from .inputs import Aborted, FocusLost, Input
from .maplearn import MapModel
from .match import Match
from .menus import Menus
from .scanner import scan_placement
from .screen import GameNotFound, Screen
from .strategy import Executor, hero_for, load_all, usable
from .vision import norm

log = logging.getLogger("runner")

MODE_BUTTON_TEXT = {
    "standard": "standard", "primary_only": "primaryonly", "deflation": "deflation",
    "military_only": "militaryonly", "apopalypse": "apopalypse", "reverse": "reverse",
    "magic_only": "magicmonkeysonly", "double_hp": "doublehpmoabs", "half_cash": "halfcash",
    "abr": "alternatebloonsrounds", "impoppable": "impoppable", "chimps": "chimps",
}


def _code_stamp():
    """Latest modification time of the bot's code and strategy files."""
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    files = list((root / "btd6bot").glob("*.py")) + list((root / "strategies").glob("*.yaml"))
    return max((f.stat().st_mtime for f in files), default=0)


def planner_specs(strats, account):
    from .planner import StrategySpec
    specs = []
    for s in strats.values():
        p = s.get("planner") or {}
        modes = [m for m in s.get("modes", []) if usable(s, m, account)[0]]
        if not modes:
            continue
        # Upgrade requirements only gate on towers we have evidence about: the
        # executor unlocks/skips upgrades in-game, and unproven ones would
        # otherwise lock a strategy out forever.
        reqs = {k: v for k, v in (p.get("towers") or {}).items() if k in account.unlocked_upgrades}
        reqs.update({k: [0, 0, 0] for k in (p.get("towers") or {}) if k not in reqs})
        specs.append(StrategySpec.from_any({
            "id": s["id"],
            "towers": reqs,
            "modes": modes,
            "base_success": {m: v for m, v in (p.get("base_success") or {}).items() if m in modes},
            "heroes": [hero_for(s, account)],
            "maps": p.get("maps"), "excluded_maps": p.get("excluded_maps"),
            "categories": p.get("categories"), "minutes": p.get("minutes"),
        }))
    return specs


class Bot:
    def __init__(self, account_path=None):
        self.s = Screen()
        self.inp = Input(self.s)
        self.lay = L.get(self.s.width, self.s.height)
        self.account = AccountState.load(account_path)
        self.menus = Menus(self.s, self.inp)
        self.strats = load_all()
        self.failures = 0
        self.bad = set()        # (map, mode) that failed to start this session
        self._level_synced = False

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
                        "profile", "overwrite"):
                self.inp.click(0.044, 0.055)  # back arrow
                time.sleep(1.0)
            elif st == "level_up":
                self.menus.handle_level_up()
            elif st == "tower_choice":
                self._tower_choice()
            elif st == "in_game":
                self.inp.click(*self.lay["gear"])
                time.sleep(0.8)
            else:
                # transitions read as "unknown" for a moment: wait before acting,
                # and only fall back to the back arrow after repeated unknowns
                if not self.menus.dismiss_popup():
                    time.sleep(1.5)
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
        for attempt in range(4):
            self.inp.click(0.5, 0.88)  # PLAY
            time.sleep(1.5)
            st = self.menus.identify()
            if st == "map_select":
                break
            log.info("after PLAY: %s", st)
            if st != "main_menu":
                self.menus.dismiss_popup()
                self.to_main_menu()
        else:
            return False
        self.inp.click(0.044, 0.154)  # search (magnifier)
        time.sleep(1.0)
        self.inp.click(0.52, 0.04)    # focus the search box
        time.sleep(0.4)
        self.inp.type_text(map_name)
        time.sleep(1.5)
        self.menus.read()
        target = norm(map_name)
        for w in sorted(self.menus.words, key=lambda w: (w.y, w.x)):
            if w.y < 0.1 or w.y > 0.9:
                continue  # the search box itself / bottom buttons
            if target in norm(w.text) or norm(w.text) in target and len(norm(w.text)) > 4:
                self.inp.click(w.x, min(0.95, w.y + 0.1))  # thumbnail sits under the name
                time.sleep(1.5)
                return self.menus.identify() == "difficulty"
        return False

    def start(self, plan):
        if not self.open_map(plan.map):
            log.error("could not open map %s", plan.map)
            return False
        self.menus.read()
        if not self.menus.click_word(plan.difficulty, dy=-0.09, region=(0, 0.3, 1, 0.7)):
            return False
        time.sleep(1.0)
        if self.menus.identify() != "mode_select":
            return False
        if not self.menus.click_word(MODE_BUTTON_TEXT.get(plan.mode, plan.mode), dy=-0.08):
            return False
        for _ in range(8):  # loading, overwrite prompts, mode intro popups
            time.sleep(1.5)
            st = self.menus.identify()
            if st == "in_game":
                return True
            if st == "overwrite":
                self.menus.click_word("ok", "yes", "overwrite")
            else:
                self.menus.dismiss_popup()
        return self.menus.identify() == "in_game"

    # -- one game ------------------------------------------------------------------
    def play(self, plan):
        strat = self.strats[plan.strategy_id]
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
        from .strategy import MODE_TOWER_FILTER
        roster = g.probe_roster()  # the save file is the truth, not our notes
        only = MODE_TOWER_FILTER.get(plan.mode_key)  # restricted modes hide other towers
        for kind, ok in roster.items():
            if ok:
                self.account.unlocked_towers.add(kind)
            elif not only or T.TOWERS[kind]["category"] == only:
                self.account.unlocked_towers.discard(kind)
        self.account.save()
        from .strategy import rules
        # Reverse runs the same track backwards: its progress map is mirrored
        key = plan.map + (" reverse" if rules(plan.mode_key).get("reversed") else "")
        model = MapModel.load(key, self.lay["playfield"])
        if key != plan.map and not model.scanned("land"):
            base = MapModel.load(plan.map, self.lay["playfield"])
            model.scan = dict(base.scan)  # placement is identical
        if not model.scanned("land"):
            log.info("first visit to %s: scanning placement", plan.map)
            scan_placement(g, model, "dart", "land")
            model.save()
        ex = Executor(g, model, strat, plan.mode_key, self.account)
        res = Match(g, self.menus, model, ex, self.account,
                    on_tower_choice=tower_chooser(self.account)).play()
        won = res.get("outcome") == "victory"
        self.account.record_result(plan.map, plan.mode_key, plan.strategy_id, won,
                                   round_reached=res.get("round"), minutes=res.get("minutes"),
                                   hero=hero)
        self.account.save()
        if won:
            self.menus.leave_victory()
        else:
            self.menus.leave_defeat()
        return res

    def run(self, hours=8.0):
        end = time.time() + hours * 3600
        code_stamp = _code_stamp()
        while time.time() < end:
            if _code_stamp() != code_stamp:
                # between games: exit so the supervisor restarts us on the new code
                log.warning("code or strategies changed - exiting to reload")
                raise SystemExit(4)
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
                self.read_level()
                plan = self.next_plan()
                if plan is None:
                    log.error("planner has nothing to play")
                    return
                log.info("NEXT: %s", plan.reason)
                if not self.start(plan):
                    log.error("failed to start %s %s - skipping it this session",
                              plan.map, plan.mode_key)
                    self.bad.add((plan.map, plan.mode_key))
                    self.failures += 1
                    continue
                res = self.play(plan)
                log.info("RESULT %s", res)
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

    def account_selected_hero(self):
        return getattr(self.account, "selected_hero", None) or "quincy"

    def select_hero(self, hero):
        """Hero choice happens on the map/difficulty screen ('Change Hero'),
        which we pass through right before the game. Until the hero menu has
        been calibrated live this only records the wish and keeps the current
        hero, so the game always matches what Game() is told."""
        log.info("strategy prefers %s; hero switching not calibrated yet - keeping %s",
                 hero, self.account_selected_hero())

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
            if (c.map, c.mode) in self.bad:
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
