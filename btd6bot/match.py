"""Playing one game from the first placement to the victory/defeat screen."""
import logging
import time

from . import towers as T
from .maplearn import PathTracer

log = logging.getLogger("match")


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
        while time.time() - t < max_seconds and idle < 2:
            cash = self.g.cash_stable()
            if self.ex.tick(cash, self.g.round()):
                idle = 0
            else:
                idle += 1
        return self.ex.defended()

    def play(self, max_minutes=60):
        if not self.setup():
            raise RuntimeError("no defence could be placed - refusing to start the round")
        self.g.go_fast(allow_start=True)
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
                if st in ("in_game", "unknown"):
                    self.menus.dismiss_popup()
                else:
                    self._off_screen(st)
                continue
            self.tracer.feed(f, self._exclude())
            dropped = False
            if now - t_hud > 0.35:
                t_hud = now
                cash = self.g.hud.cash(f)
                rnd = self.g.hud.round(f)
                lives = self.g.hud.lives(f)
                if (cash is None or lives is None) and self.g.close_panels():
                    continue
                if lives is not None and last_lives is not None and lives < last_lives <= lives + 50:
                    self.stats["lives_lost"] += last_lives - lives
                    dropped = True
                    log.warning("lost %d lives (now %d)", last_lives - lives, lives)
                if lives is not None:
                    last_lives = lives
                if rnd is not None and last_round is not None and rnd == last_round + 1:
                    self.tracer.end_round()
                    self.tracer.start_round()
                    self.stats["rounds"] += 1
                    if self.stats["rounds"] % 5 == 0:
                        self.m.save()
                    log.info("round %d  cash %s  lives %s", rnd, cash, lives)
                if rnd is not None and (last_round is None or rnd >= last_round):
                    last_round = rnd
                if self.ex.tick(cash, last_round, lives_dropped=dropped):
                    if dropped:
                        self.stats["panic"] += 1
                    t_hud = 0  # re-read cash right away after spending
                st = self.g.button_state()
                if st == "play_run":
                    self.g.go_fast(allow_start=False)
                elif st == "play_idle" and self.ex.defended():
                    self.g.go_fast(allow_start=True)
            if now - t_ability > 6 and any(p.kind == "hero" for p in self.g.towers.values()):
                t_ability = now
                self._abilities(last_round)
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

    def _abilities(self, rnd):
        hero = T.HEROES.get(self.g.hero, {})
        for i, ab in enumerate(hero.get("abilities", []), start=1):
            if ab.get("use") == "on_cooldown":
                self.g.ability(i)

    def _off_screen(self, st=None):
        st = st or self.menus.identify()
        log.info("off game screen: %s", st)
        if st in ("victory", "defeat"):
            return st
        if st == "level_up":
            self.menus.handle_level_up()
        elif st == "tower_choice":
            name = self.menus.handle_tower_choice(self.on_tower_choice or (lambda c, o: None))
            tid = T.find_tower(name) if name else None
            if tid and self.account is not None:
                self.account.unlock_tower(tid)
                self.account.save()
                log.info("unlocked tower %s", tid)
        elif st == "upgrade_tree":
            self.g.leave_tree()
        elif st == "pause":
            self.menus.click_word("continue")
        elif st == "in_game":
            return None
        else:
            if not self.menus.dismiss_popup():
                time.sleep(0.8)
        return None

    def _finish(self, outcome, rnd):
        self.tracer.end_round()
        self.m.save()
        self.stats.update(outcome=outcome, round=rnd, minutes=(time.time() - self.stats["start"]) / 60)
        log.info("game over: %s", self.stats)
        return self.stats
