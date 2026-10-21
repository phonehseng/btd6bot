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
from .screen import Screen
from .strategy import Executor, load_all, usable
from .vision import norm

log = logging.getLogger("runner")

MODE_BUTTON_TEXT = {
    "standard": "standard", "primary_only": "primaryonly", "deflation": "deflation",
    "military_only": "militaryonly", "apopalypse": "apopalypse", "reverse": "reverse",
    "magic_only": "magicmonkeysonly", "double_hp": "doublehpmoabs", "half_cash": "halfcash",
    "abr": "alternatebloonsrounds", "impoppable": "impoppable", "chimps": "chimps",
}


def planner_specs(strats, account):
    from .planner import StrategySpec
    specs = []
    for s in strats.values():
        p = s.get("planner") or {}
        modes = [m for m in s.get("modes", []) if usable(s, m, account)[0]]
        if not modes:
            continue
        specs.append(StrategySpec.from_any({
            "id": s["id"],
            "towers": p.get("towers") or {},
            "modes": modes,
            "base_success": {m: v for m, v in (p.get("base_success") or {}).items() if m in modes},
            "heroes": [s["hero"]] if s.get("hero") else [],
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

    # -- navigation ---------------------------------------------------------------
    def to_main_menu(self, tries=12):
        for _ in range(tries):
            st = self.menus.identify()
            log.info("screen: %s", st)
            if st == "main_menu":
                return True
            if st == "pause":
                self.menus.click_word("home")
            elif st == "victory":
                self.menus.leave_victory()
            elif st == "defeat":
                self.menus.leave_defeat()
            elif st in ("map_select", "difficulty", "mode_select", "hero_select", "upgrade_tree"):
                self.inp.click(0.027, 0.05)  # back arrow
                time.sleep(1.0)
            elif st == "level_up":
                self.menus.handle_level_up()
            elif st == "tower_choice":
                self._tower_choice()
            elif st == "in_game":
                self.inp.click(*self.lay["gear"])
                time.sleep(0.8)
            else:
                if not self.menus.dismiss_popup():
                    self.inp.click(0.027, 0.05)
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
        if lvl and 1 <= lvl <= 999:
            events = self.account.sync_level(lvl)
            for e in events:
                log.info(e)
            # tower choices are made on screen as they come up; don't queue them
            self.account.pending_tower_choices.clear()
            self.account.save()
        return lvl

    def open_map(self, map_name):
        """Main menu -> map select -> search -> map's difficulty screen."""
        self.inp.click(0.5, 0.88)  # PLAY
        time.sleep(1.5)
        if self.menus.identify() != "map_select":
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
            raise RuntimeError(f"could not open map {plan.map}")
        if not self.menus.click_word(plan.difficulty, dy=-0.09):
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
        hero = plan.hero or strat.get("hero") or "quincy"
        g = Game(self.s, self.inp, self.lay, difficulty=diff, hero=hero)
        self.menus.g = g
        roster = g.probe_roster()  # the save file is the truth, not our notes
        for kind, ok in roster.items():
            if ok:
                self.account.unlocked_towers.add(kind)
            else:
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
        from .planner import next_game
        end = time.time() + hours * 3600
        while time.time() < end:
            self.s.focus()
            if not self.to_main_menu():
                log.error("cannot reach main menu")
                time.sleep(5)
                continue
            self.read_level()
            plan = next_game(self.account, planner_specs(self.strats, self.account))
            if plan is None:
                log.error("planner has nothing to play")
                return
            log.info("NEXT: %s", plan.reason)
            try:
                if not self.start(plan):
                    log.error("failed to start %s %s", plan.map, plan.mode_key)
                    self.failures += 1
                    continue
                res = self.play(plan)
                log.info("RESULT %s", res)
                self.failures = 0
            except Aborted:
                raise
            except FocusLost as e:
                log.warning("%s - waiting for the game to be in front again", e)
                time.sleep(10)
                continue
            except Exception:
                log.exception("game loop error - recovering to main menu")
                self.failures += 1
            if self.failures >= 5:
                log.error("too many consecutive failures; stopping")
                return
