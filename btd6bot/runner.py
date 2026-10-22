"""Top level: pick the next game, navigate to it, play it, record it, repeat."""
import logging
import time

from . import layout as L
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


ROOT_DIR = __import__("pathlib").Path(__file__).resolve().parents[1]
ID_CHECK_EVERY = 10                   # games between account (User ID) checks
ACH_EVERY = 6 * 3600                   # seconds between achievement scans
PAUSE_FILE = ROOT_DIR / "PAUSE"        # create it to park the bot at the main menu
STATE_FILE = ROOT_DIR / "logs" / "state.txt"


def set_state(text):
    try:
        STATE_FILE.parent.mkdir(exist_ok=True)
        STATE_FILE.write_text(time.strftime("%Y-%m-%d %H:%M:%S ") + text + "\n", encoding="utf-8")
    except OSError:
        pass


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

    def sync_medals(self, map_name, label):
        """Adopt the medals the save file shows on this map's card."""
        from .account import canonical_map
        from .medals import read_card
        seen = read_card(self.s.grab(), label.x, label.y)
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
            self.menus.read()
            if self.menus.click_word(MODE_BUTTON_TEXT.get(plan.mode, plan.mode), dy=-0.08):
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
        from .strategy import MODE_TOWER_FILTER
        # the save file is the truth, not our notes: probe once per session
        # (later unlocks are seen on the level-up screen)
        roster = {} if self._roster_done else g.probe_roster()
        self._roster_done = True
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
                if self.account.player_level >= 30 and self._games_since_mk >= 3:
                    self._games_since_mk = 0
                    try:  # spend new Monkey Knowledge points (MM / XP boosts first)
                        got = Knowledge(self.s, self.inp, self.menus, self.account).spend()
                        if got:
                            log.info("Monkey Knowledge: %s", got)
                    except (FocusLost, Aborted):
                        raise
                    except Exception:
                        log.exception("Monkey Knowledge spending failed")
                    self.to_main_menu()
                if time.time() - self._ach_at > ACH_EVERY:
                    self._ach_at = time.time()
                    _ach_mark(self._ach_at)
                    try:  # claim finished achievements' rewards, refresh progress
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
                set_state(f"playing {plan.map} {plan.mode_key}")
                self._mm_before = self.read_mm()
                try:  # spend tower XP on this plan's upgrades before it needs them
                    got = unlock_for_strategy(self.s, self.inp, self.menus, self.account,
                                              self.strats[plan.strategy_id])
                    if got:
                        log.info("unlocked before the game: %s", got)
                except (FocusLost, Aborted):
                    raise
                except Exception:
                    log.exception("XP spending failed - continuing")
                    self.to_main_menu()
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
            sync_all(self.s, self.inp, self.menus, self.account)
            mark_synced(uid)
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
