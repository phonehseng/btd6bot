"""Playing one game from the first placement to the victory/defeat screen."""
import logging
import time

from . import status
from .vision import norm
from . import towers as T
from .abilities import AbilityPlanner
from .bloonwatch import BloonWatch
from .forecast import RoundForecast

WATCH_EVERY = 0.2       # seconds between looks of the bloon watch during a round
EMPTY_LOOK_GAP = 0.1    # seconds between looks at the empty map before round 1
from .maplearn import PathTracer

log = logging.getLogger("match")
BANANA_EVERY = 2.0   # seconds between passes over the bananas around farms


class LivesTracker:
    """The confirmed lives count, from noisy OCR reads of the HUD.

    * Leaks: the median of the last 5 reads (OCR flickers 120/121) falling
      below the confirmed count is a leak of any size - a MOAB leak is the
      worst case, not noise.
    * Rises: lives only go up by a few at a time, so a read more than
      RISE_LIMIT above the confirmed count is ignored (Easy's 200 was read as
      "2001" for a whole game, and letting that in would later look like a
      huge leak and trigger panic buying) ...
    * ... unless RISE_VOTES reads in a row agree on it. Without this, one
      wrong LOW value (a bad first read, say 15 for 150) was confirmed
      forever: every true read was then "too high" and ignored, and leaks
      were never noticed again.
    * A read above `max_lives` (twice the mode's starting lives plus 25, room
      for bonus lives) is never believed, however steady - not even as the
      first read of the game, which would turn every true read into a leak.
    """
    RISE_LIMIT = 50
    RISE_VOTES = 4

    def __init__(self, start_lives=None):
        self.confirmed = None
        self.reads = []                       # last 5 accepted reads
        self.max_lives = 2 * start_lives + 25 if start_lives else None
        self._cand, self._votes = None, 0     # an upward correction being voted on

    def median(self):
        return sorted(self.reads)[len(self.reads) // 2] if self.reads else None

    def update(self, read):
        """Feed one read (None = unreadable). Returns the lives lost (0 if none)."""
        if read is not None and self.max_lives and read > self.max_lives:
            read = None    # impossible for this mode, even as the very first read
        if read is not None and self.confirmed is not None and read > self.confirmed + self.RISE_LIMIT:
            if not self._vote_rise(read):
                return 0
        elif read is not None:
            self._cand, self._votes = None, 0
        if read is not None:
            self.reads = (self.reads + [read])[-5:]
        med = self.median()
        if med is not None and self.confirmed is not None and med < self.confirmed:
            lost, self.confirmed = self.confirmed - med, med
            return lost
        if self.confirmed is None and med is not None:
            self.confirmed = med
        return 0

    def _vote_rise(self, read):
        """A read far above the confirmed count. True once RISE_VOTES reads in
        a row agree (within 2): the count then restarts from it. False while
        it is still only a suspected misread."""
        if self._cand is not None and abs(read - self._cand) <= 2:
            self._votes += 1
        else:
            self._cand, self._votes = read, 1
        if self._votes < self.RISE_VOTES:
            return False
        log.warning("lives tracking corrected %s -> %s (%d agreeing reads)",
                    self.confirmed, read, self._votes)
        self.confirmed, self.reads = read, []
        self._cand, self._votes = None, 0
        return True


def _hero_id(text):
    n = "".join(c for c in text.lower() if c.isalnum())
    for hid, h in T.HEROES.items():
        if len(n) >= 4 and "".join(c for c in h["name"].lower() if c.isalnum()) == n:
            return hid
    return None


class Match:
    def __init__(self, game, menus, model, executor, account=None, on_tower_choice=None):
        self.g = game
        self.menus = menus
        self.m = model
        self.ex = executor
        self.account = account
        self.tracer = PathTracer(model)
        self.on_tower_choice = on_tower_choice
        self.stats = {"start": time.time(), "rounds": 0, "lives_lost": 0, "panic": 0}
        self._prev_lives_read = None
        self._lives = LivesTracker((getattr(executor, "rules", None) or {}).get("lives"))
        self._round_cand, self._round_votes = None, 0
        self._last_buy = time.time()
        self._last_wait_log = 0.0
        self._t_bananas = 0.0      # last pass over the farms' bananas
        self.abil = AbilityPlanner(getattr(game, "hero", None), getattr(executor, "rules", None))
        self._in_round = False
        # the damage model's view of each round as it starts (forecast.py)
        self.forecast = RoundForecast(getattr(model, "name", None), getattr(executor, "mode", None))
        self._crisis_round = None
        # how far along the route the bloons really get (bloonwatch.py; observe only)
        self.watch = self._make_watch()
        self._t_watch = 0.0
        self.depths = []           # per-round summaries of the watch

    def _make_watch(self):
        try:
            lay = getattr(self.g, "lay", None) or {}
            panels = [lay[s]["box"] for s in ("upg_left", "upg_right") if s in lay]
            hud = [lay[s] for s in ("lives", "cash", "round") if s in lay]
            return BloonWatch(getattr(self.m, "name", None), self.m.playfield, panels, hud)
        except Exception as e:      # an observer must never cost a game
            log.info("bloon watch not available: %s", e)
            return None

    def _exclude(self):
        out = []
        for p in self.g.towers.values():
            cx, cy = self.m.frac_to_cell(p.x, p.y)
            if p.kind == "hero":
                r = self.m.radius_cells(T.HEROES.get(self.g.hero, {}).get("range") or 40, self.g.s.width)
            else:
                r = self.m.radius_cells(T.TOWERS[p.kind].get("range") or 40, self.g.s.width)
            out.append((cx, cy, min(r * 1.15, 25)))
        return out

    def setup(self, max_seconds=60):
        """Before the first round: buy everything affordable from the plan.
        Fast Track starts Hard at round ~22 with thousands in cash (double with
        Double Cash): that money must become a full defence before Play, since
        those rounds come fast and mixed - so spend down, plan first, then surplus."""
        t = time.time()
        idle = 0
        rnd = self.g.round()
        late = rnd is not None and rnd >= 10
        if late:
            max_seconds = 150
            log.info("game starts at round %d (Fast Track?) - building the full defence first", rnd)
        # failed spots are blocked one by one, so keep trying for a while
        # before concluding nothing can be placed (never start undefended).
        # On a late (Fast Track) start every dollar goes in before Play: Dark
        # Path Hard started round 22 with $6,025 unspent - the old loop gave up
        # after 4 idle passes whatever the cash - and lost 47 lives in seconds.
        cash = None
        while time.time() - t < max_seconds and idle < 8:
            cash = self.g.cash_stable()
            bought = self.ex.tick(cash, rnd)
            if not bought and late and cash is not None and cash > 600:
                bought = self.ex.surplus(cash, rnd)
            if bought:
                idle = 0
            else:
                idle += 1
            if self.ex.defended() and idle >= 2 and (not late or (cash or 0) < 600):
                break
        if late and cash is not None and cash >= 600:
            log.warning("starting round %s with $%d unspent: %s", rnd, cash,
                        getattr(self.ex, "waiting", "nothing more could be bought"))
        if not self.ex.defended():
            self._place_starter(rnd)
        return self.ex.defended()

    def _place_starter(self, rnd, tries=6):
        """Only the hero is down and the plan's next tower is not affordable
        yet (Easy: hero $460 of $650, tack $260): buy the cheapest opener
        tower near the entrance so no round starts with the hero alone."""
        for kind in self.ex.CHEAP_OPENERS:
            if not self.ex.kind_allowed(kind):
                continue
            step = {"do": "place", "id": "starter", "kind": kind, "role": "dps", "segment": [0.05, 0.45]}
            for _ in range(tries):     # each refused spot is blocked; try the next
                if self.ex.try_step(step, self.g.cash_stable(), rnd) == "done" or self.ex.defended():
                    log.info("starter tower placed: %s", kind)
                    return True
                time.sleep(0.3)
        return False

    def play(self, max_minutes=None):
        if max_minutes is None:
            # long modes need longer: CHIMPS (rounds 6-100) runs 40-50 minutes
            # on fast forward; give every game about 45 s per round, at least an hour
            rounds = self.ex.rules.get("end_round", 80) - self.ex.rules.get("start_round", 1) + 1
            max_minutes = max(60, 0.75 * rounds)
        if not self.setup():
            raise RuntimeError("no defence could be placed - refusing to start the round")
        self._learn_empty_map()
        self.g.go_fast(allow_start=True)
        self._in_round = True
        last_round = self.g.round()
        self._lives.update(self.g.lives())
        self.tracer.start_round()
        t_hud = t_ability = 0.0
        cash = None
        while time.time() - self.stats["start"] < max_minutes * 60:
            f = self.g.fresh()
            if not self.g.in_game(f):
                outcome = self._off_screen()
                if outcome:
                    return self._finish(outcome, last_round)
                continue
            now = time.time()
            end_round = self.ex.rules.get("end_round", 80)
            # the end screen is looked for from 3 rounds before the end: a round
            # reader stuck at 39 of 40 once hid a VICTORY screen for 4 minutes
            # while placement clicks landed on it (Downstream Easy)
            if last_round is not None and last_round >= end_round - 3 and now - getattr(self, "_t_end", 0) > 2.5:
                # final round: the victory overlay dims but does not hide the HUD
                self._t_end = now
                st = self.menus.identify()
                if st in ("victory", "defeat") and self._real_end(st, f):
                    return self._finish(st, last_round)
            if self._frozen(f, now):
                # a modal popup pauses the game while the HUD stays visible
                st = self.menus.identify()
                log.info("screen frozen (%s) - looking for a popup", st)
                if st in ("victory", "defeat") and self._real_end(st, f):
                    return self._finish(st, last_round)  # the end screen overlays the HUD
                if st == "defeat":
                    self.g.close_panels()
                    continue
                if st in ("in_game", "unknown"):
                    self.menus.dismiss_popup()
                else:
                    self._off_screen(st)
                continue
            if self.m.rounds_traced < 25:  # the track is learned by then
                self.tracer.feed(f, self._exclude())
            if self._in_round and now - self._t_watch > WATCH_EVERY:
                self._t_watch = now
                self._watch_look(f, now)
            dropped = False
            if now - t_hud > 0.35:
                t_hud = now
                cash = self.g.hud.cash(f)
                rnd = self.g.hud.round(f)
                lives = self.g.hud.lives(f)
                if (cash is None or lives is None) and self.g.close_panels():
                    continue
                # leaks, misreads and upward corrections: see LivesTracker
                lost = self._lives.update(lives)
                if lost:
                    self.stats["lives_lost"] += lost
                    dropped = True
                    log.warning("lost %d lives (now %d)", lost, self._lives.confirmed)
                    # abilities first: a key press takes milliseconds, the panic
                    # purchases below take seconds (Water Park: Rapid Shot came
                    # 4 s after the first leak, behind the buying)
                    if self.g.towers:
                        t_ability = now
                        self._abilities(last_round, dropped=True)
                self._prev_lives_read = lives
                # rounds only move forward, one or two at a time
                if rnd is not None and last_round is not None and last_round < rnd <= last_round + 2:
                    self.tracer.end_round()
                    self.tracer.start_round()
                    self.stats["rounds"] += rnd - last_round
                    if self.stats["rounds"] % 5 == 0:
                        self.m.save()
                    self._watch_round_end(last_round)
                    log.info("round %d  cash %s  lives %s", rnd, cash, lives)
                    status.in_game(f"round {rnd}, ${cash}, {self._lives.confirmed} lives")
                    last_round = rnd
                    self._forecast_round(rnd)
                    # once a round: a tower whose range barely reaches the
                    # track is sold, its cash goes to towers that pop bloons
                    try:
                        self.ex.sell_useless(rnd, lives_dropped=dropped)
                    except Exception:
                        log.exception("selling useless towers failed - carrying on")
                elif rnd is not None and rnd != last_round:
                    # a reading outside the expected step: adopt it only if it
                    # persists (recovers from a bad first read)
                    if rnd == self._round_cand:
                        self._round_votes += 1
                    else:
                        self._round_cand, self._round_votes = rnd, 1
                    # small corrections need 4 agreeing reads, big jumps (OCR
                    # '11' -> '711') far more - a wrong round misfires threats
                    big = last_round is not None and abs(rnd - last_round) > 3
                    if last_round is None or self._round_votes >= (15 if big else 4):
                        log.info("round tracking reset %s -> %s", last_round, rnd)
                        last_round = rnd
                bought = self.ex.tick(cash, last_round, lives_dropped=dropped)
                if getattr(self.g, "unconfirmed_streak", 0) >= 2:
                    # Placements that leave no tower are clicks landing on
                    # something else - an end screen or a popup over the game
                    # (a missed Victory screen once took four minutes of them):
                    # look at the screen before clicking any more.
                    self.g.unconfirmed_streak = 0
                    st = self.menus.identify()
                    if st in ("victory", "defeat") and self._real_end(st, self.g.fresh()):
                        return self._finish(st, last_round)
                    if st not in ("in_game", "unknown"):
                        outcome = self._off_screen(st)
                        if outcome:
                            return self._finish(outcome, last_round)
                        continue
                crisis = dropped or self._in_crisis(last_round)
                saving = (getattr(self.ex, "wait_cost", None) and cash is not None
                          and cash < self.ex.wait_cost and not crisis)
                # Saving up for a big upgrade is fine, briefly - these are seconds
                # of fast-forward, several rounds; never while lives are falling
                # (losses showed $3-6k idle during leaks) or in a round the
                # damage model expects to leak.
                patience = 0 if crisis else (12 if saving else 3)
                if not bought and cash is not None and cash > 800 and now - self._last_buy > patience:
                    # cash is piling up while the plan waits: say why, then spend it
                    if now - self._last_wait_log > 20:
                        self._last_wait_log = now
                        log.info("idle with $%d: %s", cash, getattr(self.ex, "waiting", "?"))
                    bought = self.ex.surplus(cash, last_round)
                if bought:
                    self._last_buy = now
                    if dropped:
                        self.stats["panic"] += 1
                    t_hud = 0  # re-read cash right away after spending
                # bananas pay only when the cursor passes over them
                if now - self._t_bananas > BANANA_EVERY:
                    self._t_bananas = now
                    got = self.g.collect_bananas()
                    if got:
                        self.stats["banana_moves"] = self.stats.get("banana_moves", 0) + got
                st = self.g.button_state()
                if st in ("play_idle", "play_run", "play_fast"):
                    self._in_round = st != "play_idle"
                if st == "play_run":
                    self.g.go_fast(allow_start=False)
                elif st == "play_idle" and self.ex.defended() and not self._hold_round(last_round, cash):
                    self.g.go_fast(allow_start=True)
                    self._in_round = True
            if self.g.towers and now - t_ability > 1.0:
                t_ability = now
                self._abilities(last_round)
            time.sleep(0.02)
        return self._finish("timeout", last_round)

    def _hold_round(self, rnd, cash):
        """Keep the next round from starting while it brings a bloon the defence
        cannot pop and the answer is affordable now (Executor.hold_round; the
        executor bounds the wait, so a failing purchase never stalls a game)."""
        hold = getattr(self.ex, "hold_round", None)
        try:
            return bool(hold and hold(rnd, cash))
        except Exception as e:   # the check must never stop the game from going on
            log.warning("hold_round failed: %r", e)
            return False

    def _frozen(self, f, now):
        """True if the play field has not changed for ~2 s (game paused by a popup)."""
        import cv2
        import numpy as np
        thumb = cv2.cvtColor(cv2.resize(f, (96, 60), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
        prev = getattr(self, "_thumb", None)
        self._thumb = thumb
        if prev is None or np.abs(thumb.astype(int) - prev.astype(int)).mean() > 0.4:
            self._still_since = now
            return False
        if now - getattr(self, "_still_since", now) > 2.0:
            self._still_since = now
            return True
        return False

    def _forecast_round(self, rnd):
        """Ask the damage model about the round that just started; a round it
        expects to leak becomes a crisis round (see forecast.py)."""
        margin = self.forecast.margin(list(self.g.towers.values()), rnd)
        if margin is None:
            return
        if self.forecast.is_crisis(margin):
            self._crisis_round = rnd
            log.warning("round %d: the damage model rates the defence %.2f - crisis round: "
                        "abilities as soon as bloons are out, no saving up", rnd, margin)
        else:
            log.info("round %d: the damage model rates the defence %.2f", rnd, margin)

    # -- the bloon watch (bloonwatch.py): observe only ------------------------------
    def _learn_empty_map(self):
        """Look at the empty map (towers placed, no bloons yet, no panel
        open) for about a second and a half before round 1 starts."""
        if self.watch is None:
            return
        try:
            self.g.close_panels()
            for _ in range(15):
                self.watch.learn_empty(self.g.fresh())
                time.sleep(EMPTY_LOOK_GAP)
        except Exception:
            log.exception("bloon watch: learning the empty map failed - watch off")
            self.watch = None

    def _watch_look(self, f, now):
        if self.watch is None:
            return
        try:
            self.watch.look(f, now, [p for p in self.g.towers.values()])
        except Exception:
            log.exception("bloon watch failed - off for the rest of this game")
            self.watch = None

    def _watch_round_end(self, rnd):
        """Log how far the bloons got in the round that just ended."""
        if self.watch is None or rnd is None:
            return
        try:
            s = self.watch.end_round(rnd, label=f"{getattr(self.m, 'name', '')}_{getattr(self.ex, 'mode', '')}")
        except Exception:
            log.exception("bloon watch summary failed - watch off")
            self.watch = None
            return
        if s:
            self.depths.append(s)
            log.info("round %d: bloons got %.0f%% along the route at most, past 80%% in %.0f%% of %d looks",
                     rnd, 100 * s["deepest"], 100 * s["deep_share"], s["looks"])

    def _in_crisis(self, rnd):
        return rnd is not None and self._crisis_round == rnd

    def _abilities(self, rnd, dropped=False):
        """Press the ability hotkeys the planner picks (see abilities.py)."""
        try:
            self.abil.update_towers(list(self.g.towers.values()), rnd)
            keys = self.abil.decide(time.time(), rnd, self._in_round, lives_dropped=dropped,
                                    crisis=self._in_crisis(rnd))
        except Exception:  # never let ability bookkeeping end a game
            log.exception("ability planner failed")
            return
        for key, name, reason in self.abil.last_fired:
            (log.info if reason != "cooldown" else log.debug)("ability %d (%s): %s", key, name, reason)
        for key in keys:
            self.g.ability(key)

    # Screens that only exist outside a game: seeing one of these a few times
    # in a row means the game already ended (e.g. a click meant for the map
    # landed on the defeat screen's Home button).
    MENU_SCREENS = ("main_menu", "map_select", "difficulty", "mode_select", "monkeys_menu", "title")

    def _off_screen(self, st=None):
        st = st or self.menus.identify()
        log.info("off game screen: %s", st)
        if st == "victory":
            return st
        if st == "defeat":
            # a defeat needs evidence: lives near zero (the Legends page once
            # read as "defeat" with all 200 lives - a game that had been WON)
            lives = self._lives.median()
            if lives is None or lives <= 20:
                return st
            log.warning("'defeat' read with %s lives - not believed", lives)
        if st in self.MENU_SCREENS:
            self._menu_reads = getattr(self, "_menu_reads", 0) + 1
            if self._menu_reads >= 3:
                lives = self._lives.median()
                outcome = "defeat" if lives is None or lives <= 20 else "abandoned"
                log.warning("back at the menus mid-game (%s; last lives %s) - recording %s", st, lives, outcome)
                return outcome
        else:
            self._menu_reads = 0
        if st != "unknown":
            self._unknown = 0
        if st in ("level_up", "hero_unlock"):
            self.menus.handle_level_up()  # both continue with a click
            if st == "hero_unlock" and self.account is not None:
                for w in self.menus.words:
                    hid = _hero_id(w.text)
                    if hid:
                        self.account.unlocked_heroes.add(hid)
                        self.account.save()
                        log.info("hero unlocked: %s", hid)
        elif st == "tower_choice":
            name = self.menus.handle_tower_choice(self.on_tower_choice or (lambda c, o: None))
            tid = T.find_tower(name) if name else None
            if tid and self.account is not None:
                self.account.unlock_tower(tid)
                self.account.save()
                log.info("unlocked tower %s", tid)
                if len(getattr(self.menus, "last_offered", [])) == 1:
                    # nothing else was offered: the rest of this category is owned
                    cat = T.TOWERS[tid]["category"]
                    for k, t in T.TOWERS.items():
                        if t["category"] == cat and k not in T.GIFT_BOX_TOWERS:
                            self.account.unlocked_towers.add(k)
                    self.account.save()
        elif st == "upgrade_tree":
            self.g.leave_tree()
        elif st == "pause":
            self.menus.click_word("continue")
        elif st == "in_game":
            return None
        else:
            if not self.menus.dismiss_popup():
                # full-screen announcements (new hero, rewards) continue on click
                self._unknown = getattr(self, "_unknown", 0) + 1
                from .menus import page_forbidden
                if self._unknown >= 3 and not page_forbidden(self.menus.words):
                    log.info("unknown screen x%d - clicking to continue", self._unknown)
                    self.menus.inp.click(0.5, 0.5)
                time.sleep(0.8)
        return None

    def _real_end(self, st, f):
        """A defeat needs the lives counter to agree: a word like 'defeat' can
        show up in tower/upgrade panels and once made the bot quit three games
        it was winning at full lives."""
        if st != "defeat":
            return True
        lives = self.g.hud.lives(f) if f is not None else None
        known = self._lives.median()
        if lives and lives > 0 and (known is None or known > 0):
            hits = [w.text for w in self.menus.words
                    if any(k in norm(w.text) for k in ("defeat", "gameover", "bloonsleaked", "youlost"))]
            log.warning("ignoring 'defeat' screen: lives still %s (matched %s)", lives, hits)
            try:
                import cv2
                cv2.imwrite(f"logs/false_defeat_{int(time.time())}.png", f)
            except Exception:
                pass
            return False
        return True

    def _finish(self, outcome, rnd):
        try:
            from .maplearn import record_spot_results
            record_spot_results(self.m, list(self.g.towers.values()))
        except Exception:
            log.exception("spot learning failed")
        self.tracer.end_round()
        self.m.save()
        self._watch_round_end(rnd)
        if self.depths:
            # the deepest point bloons reached in any round (bloonwatch.py)
            self.stats["bloon_depth"] = max(s["deepest"] for s in self.depths)
        self.stats.update(outcome=outcome, round=rnd, minutes=(time.time() - self.stats["start"]) / 60)
        log.info("game over: %s", self.stats)
        return self.stats
