"""Playing one game from the first placement to the victory/defeat screen."""
import logging
import time

from . import towers as T
from .abilities import AbilityPlanner
from .maplearn import PathTracer

log = logging.getLogger("match")


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
        self._lives_reads = []
        self._round_cand, self._round_votes = None, 0
        self._last_buy = time.time()
        self._last_wait_log = 0.0
        self.abil = AbilityPlanner(getattr(game, "hero", None), getattr(executor, "rules", None))
        self._in_round = False

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
        """Before round 1: buy everything affordable from the plan."""
        t = time.time()
        idle = 0
        # failed spots are blocked one by one, so keep trying for a while
        # before concluding nothing can be placed (never start undefended)
        while time.time() - t < max_seconds and idle < 8:
            cash = self.g.cash_stable()
            if self.ex.tick(cash, self.g.round()):
                idle = 0
            else:
                idle += 1
            if self.ex.defended() and idle >= 2:
                break
        return self.ex.defended()

    def play(self, max_minutes=60):
        if not self.setup():
            raise RuntimeError("no defence could be placed - refusing to start the round")
        self.g.go_fast(allow_start=True)
        self._in_round = True
        last_round = self.g.round()
        last_lives = self.g.lives()
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
            if last_round is not None and last_round >= end_round and now - getattr(self, "_t_end", 0) > 2.5:
                # final round: the victory overlay dims but does not hide the HUD
                self._t_end = now
                st = self.menus.identify()
                if st in ("victory", "defeat"):
                    return self._finish(st, last_round)
            if self._frozen(f, now):
                # a modal popup pauses the game while the HUD stays visible
                st = self.menus.identify()
                log.info("screen frozen (%s) - looking for a popup", st)
                if st in ("victory", "defeat"):
                    return self._finish(st, last_round)  # the end screen overlays the HUD
                if st in ("in_game", "unknown"):
                    self.menus.dismiss_popup()
                else:
                    self._off_screen(st)
                continue
            if self.m.rounds_traced < 25:  # the track is learned by then
                self.tracer.feed(f, self._exclude())
            dropped = False
            if now - t_hud > 0.35:
                t_hud = now
                cash = self.g.hud.cash(f)
                rnd = self.g.hud.round(f)
                lives = self.g.hud.lives(f)
                if (cash is None or lives is None) and self.g.close_panels():
                    continue
                # lives: median of the last 5 reads (OCR flickers 120/121), any
                # size of drop counts - a MOAB leak is the worst case, not noise
                if lives is not None:
                    self._lives_reads = (self._lives_reads + [lives])[-5:]
                med = sorted(self._lives_reads)[len(self._lives_reads) // 2] if self._lives_reads else None
                if med is not None and last_lives is not None and med < last_lives:
                    self.stats["lives_lost"] += last_lives - med
                    dropped = True
                    log.warning("lost %d lives (now %d)", last_lives - med, med)
                    last_lives = med
                elif last_lives is None and med is not None:
                    last_lives = med
                self._prev_lives_read = lives
                # rounds only move forward, one or two at a time
                if rnd is not None and last_round is not None and last_round < rnd <= last_round + 2:
                    self.tracer.end_round()
                    self.tracer.start_round()
                    self.stats["rounds"] += rnd - last_round
                    if self.stats["rounds"] % 5 == 0:
                        self.m.save()
                    log.info("round %d  cash %s  lives %s", rnd, cash, lives)
                    last_round = rnd
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
                saving = getattr(self.ex, "wait_cost", None) and cash is not None                     and cash < self.ex.wait_cost and not dropped
                patience = 40 if saving else 12  # saving up for a big upgrade is fine, briefly
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
                st = self.g.button_state()
                if st in ("play_idle", "play_run", "play_fast"):
                    self._in_round = st != "play_idle"
                if st == "play_run":
                    self.g.go_fast(allow_start=False)
                elif st == "play_idle" and self.ex.defended():
                    self.g.go_fast(allow_start=True)
                    self._in_round = True
            if self.g.towers and (dropped or now - t_ability > 1.0):
                t_ability = now
                self._abilities(last_round, dropped)
            time.sleep(0.02)
        return self._finish("timeout", last_round)

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

    def _abilities(self, rnd, dropped=False):
        """Press the ability hotkeys the planner picks (see abilities.py)."""
        try:
            self.abil.update_towers(list(self.g.towers.values()), rnd)
            keys = self.abil.decide(time.time(), rnd, self._in_round, lives_dropped=dropped)
        except Exception:  # never let ability bookkeeping end a game
            log.exception("ability planner failed")
            return
        for key, name, reason in self.abil.last_fired:
            (log.info if reason != "cooldown" else log.debug)("ability %d (%s): %s", key, name, reason)
        for key in keys:
            self.g.ability(key)

    def _off_screen(self, st=None):
        st = st or self.menus.identify()
        log.info("off game screen: %s", st)
        if st in ("victory", "defeat"):
            return st
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

    def _finish(self, outcome, rnd):
        try:
            from .maplearn import record_spot_results
            record_spot_results(self.m, list(self.g.towers.values()))
        except Exception:
            log.exception("spot learning failed")
        self.tracer.end_round()
        self.m.save()
        self.stats.update(outcome=outcome, round=rnd, minutes=(time.time() - self.stats["start"]) / 60)
        log.info("game over: %s", self.stats)
        return self.stats
