"""Playing one game from the first placement to the victory/defeat screen."""
import logging
import time

from . import hudstate
from . import journal
from . import status
from . import threats as TH
from .vision import norm
from . import towers as T
from .abilities import AbilityPlanner
from .bloonwatch import BloonWatch
from . import reinforce as R
from .forecast import CRISIS_MARGIN, RoundForecast, lowest
from .towerxp import TowerXpCounter
from .carried import CarriedTowers

REINFORCE_EVERY = 2.0   # seconds between model-chosen purchases (each choice takes ~1 s)
REINFORCE_WAIT = 8.0    # ... and after a look that found nothing affordable to help
WATCH_EVERY = 0.2       # seconds between looks of the bloon watch during a round
EMPTY_LOOK_GAP = 0.1    # seconds between looks at the empty map before round 1
# Play waits while the damage model expects the coming round to leak and
# purchases are still being made (Match._hold_for_crisis): the break between
# rounds is free time to spend in.
CRISIS_HOLD_S = 20.0       # longest wait per round
CRISIS_HOLD_IDLE_S = 4.0   # ... ended early once this long passes without a purchase
CRISIS_HOLD_MIN_CASH = 300  # less than this buys nothing that matters
# Rounds played without ever seeing the Play button idle before the bot
# concludes the game's own Auto Start is on (it then cannot hold a round).
AUTO_START_ROUNDS = 8
from .maplearn import PathTracer

log = logging.getLogger("match")

# Start of the error play() raises when not even one tower could be placed
# before round 1; the runner recognises it to note placement trouble.
NO_DEFENCE_ERROR = "no defence could be placed"
BANANA_EVERY = 2.0   # seconds between passes over the bananas around farms
# Dartling Gunners (and a heli before its targeting is set) aim at the mouse:
# while the bot has nothing to click, the cursor rests on the busiest stretch
# of track instead of wherever its last click left it.
PARK_EVERY = 1.5     # seconds between checks of where the cursor rests
PARK_WINDOW = 15     # grid cells: the track density is measured over this square
PARK_SLACK = 12      # pixels: closer than this to the spot, the cursor stays put
# No-income modes (Deflation) buy the whole defence before Play and can never
# add to it, so the damage model can judge the finished build before a single
# bloon is out. Calibrated on the 26 logged Deflation games whose first
# look-ahead (rounds 31/32-41) was rated: below 0.8 were 5 of the 7 losses
# (0.06-0.78) and 1 of the 19 wins (Balance, 0.53). Leaving costs a minute;
# a loss is never acceptable.
NO_INCOME_MIN_MARGIN = 0.8


class WeakBuild(RuntimeError):
    """The finished no-income build rates too low to start: leave the game
    before round one (not a defeat) and bench this map/mode (runner.py)."""

    def __init__(self, margin, rnd):
        super().__init__(f"the finished build rates round {rnd} at {margin:.2f} "
                         f"(under {NO_INCOME_MIN_MARGIN}) - leaving before Play")
        self.margin, self.round = margin, rnd


def too_weak_to_start(ahead, rules):
    """True when `ahead` - forecast.worst's (margin, round) of the opening
    look-ahead, or None when the model cannot rate - says a buy_all_upfront
    game would lose. Modes with income can still reinforce later, and an
    unrated build is played as before."""
    return bool(rules.get("buy_all_upfront")) and ahead is not None and ahead[0] < NO_INCOME_MIN_MARGIN


def _misread_note(read, confirmed):
    """A log suffix naming the raw HUD read when it differs from the
    confirmed lives count ("" when they agree or either is unknown), so the
    round line shows the game's state and still keeps the evidence of a
    misread."""
    if read is None or confirmed is None or read == confirmed:
        return ""
    return f" (read {read})"


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
    * In a mode whose lives never change (`fixed`: Impoppable and CHIMPS,
      one life and no way to gain any) max_lives is the starting count
      itself. The lives crop starts at the heart's edge and the OCR adds a
      phantom leading 1 to it: Ancient Portal Impoppable (2026-11-05) read
      11 in 29 of 65 reads of a 1. The confirmed count survived that game,
      but a game whose first five reads median to 11 would start there and
      count the next true reads as a 10-life leak.
    """
    RISE_LIMIT = 50
    RISE_VOTES = 4

    def __init__(self, start_lives=None, fixed=False):
        self.confirmed = None
        self.reads = []                       # last 5 accepted reads
        if start_lives and fixed:
            self.max_lives = start_lives
        else:
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


class RoundVotes:
    """Decides when a round reading that is not the expected next step (one
    or two rounds on) replaces the tracked round.

    A single odd reading is usually OCR noise ('11' read as '711'), so it has
    to be confirmed by later readings. Readings used to count only when they
    were IDENTICAL - but while the bot is busy (Geared Medium, 2026-11-03:
    ticks of 10-15 s of refused placement clicks) the game moves on between
    two readings, every reading differs, and the tracked round stayed at 23
    while the game played on to round 40 and lost: no threats, crisis rounds
    or reinforcements for 17 rounds. So a reading now also agrees with the
    previous one when it is the same or as many rounds later as the time
    between them allows (the game only moves forward, at most one round per
    MIN_ROUND_SECONDS, plus MAX_STEP), and a forward jump that the elapsed time allows
    (at most one round per MIN_ROUND_SECONDS) needs only PLAUSIBLE_VOTES.
    """
    MAX_STEP = 2               # rounds the game may move on between two readings
    MIN_ROUND_SECONDS = 3.0    # no round is over faster than this, even on fast forward
    PLAUSIBLE_VOTES = 3        # forward jumps the elapsed time explains
    SMALL_VOTES = 4            # other changes of up to 3 rounds
    BIG_VOTES = 15             # anything else (a misread like '11' -> '711')

    def __init__(self):
        self.cand, self.votes = None, 0
        self.t_prev = None      # `since_change` of the previous reading

    def vote(self, read, last_round, since_change):
        """Feed one reading `read` that is not an expected step from
        `last_round`, `since_change` seconds after the tracked round last
        changed. True when the tracked round should become `read`."""
        # how far the game can have moved on since the previous reading
        step = self.MAX_STEP
        if self.t_prev is not None and since_change >= self.t_prev:
            step += (since_change - self.t_prev) / self.MIN_ROUND_SECONDS
        if self.cand is not None and self.cand <= read <= self.cand + step:
            self.votes += 1
        else:
            self.votes = 1
        self.cand, self.t_prev = read, since_change
        if last_round is None:
            return True
        jump = read - last_round
        if 0 < jump <= self.MAX_STEP + since_change / self.MIN_ROUND_SECONDS:
            need = self.PLAUSIBLE_VOTES
        else:
            need = self.SMALL_VOTES if abs(jump) <= 3 else self.BIG_VOTES
        if self.votes >= need:
            self.cand, self.votes, self.t_prev = None, 0, None
            return True
        return False


def xp_knowledge(account, rules):
    """The Monkey Knowledge the tower XP count may apply: the account's,
    except in modes that switch Monkey Knowledge off (CHIMPS), where Monkey
    Education's bonus is not paid either."""
    if (rules or {}).get("no_mk") or account is None:
        return ()
    return getattr(account, "mk_unlocked", ()) or ()


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
        rules = getattr(executor, "rules", None) or {}
        self._lives = LivesTracker(rules.get("lives"), fixed=bool(rules.get("one_life")))
        self._round_votes = RoundVotes()
        # Geared's gears turn after each round and carry their towers with
        # them: their remembered click spots are turned too (carried.py)
        try:
            self._carried = CarriedTowers.for_map(getattr(model, "name", None), model.playfield)
        except Exception:
            log.exception("could not set up towers on rotating ground - their spots stay fixed")
            self._carried = None
        # Erosion's bloons take a new path every 18 rounds: the track is
        # repainted for the round's path phase as rounds pass (_follow_track)
        self._phase_geom, self._reverse = self._path_phases(model)
        self._t_round_change = time.time()   # when the tracked round last changed
        self._last_buy = time.time()
        self._last_wait_log = 0.0
        self._t_bananas = 0.0      # last pass over the farms' bananas
        self._t_park = 0.0         # last cursor park (PARK_EVERY)
        self._park = None          # where the cursor rests: the busiest track (screen fractions)
        self.abil = AbilityPlanner(getattr(game, "hero", None), getattr(executor, "rules", None))
        self._in_round = False
        # the damage model's view of each round as it starts (forecast.py)
        self.forecast = RoundForecast(getattr(model, "name", None), getattr(executor, "mode", None),
                                      getattr(model, "sight", None),
                                      (getattr(model, "sight_height", None), getattr(model, "ground_height", None)))
        self._weak_round = None     # a round whose look-ahead is weak: reinforce (reinforce.py)
        self._t_reinforce = 0.0
        self._saving_until = 0.0    # reinforce saves for a dearer purchase until then
        self._crisis_round = None
        self._crisis_hold = {}      # round -> time Play started waiting, or False (no hold)
        self._idle_seen = False     # the Play button was seen idle between rounds
        # how far along the route the bloons really get (bloonwatch.py; observe only)
        self.watch = self._make_watch()
        # tower XP this game earns, round by round (towerxp.py): the paragon
        # focus works from the account's XP, read from the game once a day
        from .strategy import PRICE_FAMILY
        self.tower_xp = TowerXpCounter(getattr(model, "name", None),
                                       xp_knowledge(account, getattr(executor, "rules", None)),
                                       PRICE_FAMILY.get(getattr(executor, "mode", None), "medium"))
        self._t_watch = 0.0
        self.depths = []           # per-round summaries of the watch
        # the game journal (journal.py): what is bought and why, round
        # snapshots, leaks and the cause of a defeat, one file per game
        self._margins = {}         # round -> the damage model's margin as it started
        self._round_lost = 0       # lives lost in the round being played
        self._leak_rounds = set()  # rounds with a leak in the journal
        self._threat_holds = set()  # rounds whose threat hold is in the journal
        self._hud_sizes = {}        # kind -> ghost sizes for the big HUD (hudstate.tower_sizes)
        # selling is refused by Game itself in modes that forbid it (CHIMPS)
        game.no_sell = bool(getattr(executor, "no_sell", False))
        try:
            journal.start_game(getattr(model, "name", None), getattr(executor, "mode", None),
                               (getattr(executor, "strat", None) or {}).get("id"),
                               getattr(game, "hero", None), getattr(executor, "rules", None),
                               account, executor)
        except Exception:          # an observer must never cost a game
            log.exception("could not start the game journal - playing without it")
        # the big HUD's view of the match (hudstate.py; observe only)
        hudstate.start_game(map=getattr(model, "name", None), mode=getattr(executor, "mode", None),
                            strategy=(getattr(executor, "strat", None) or {}).get("id"),
                            hero=getattr(game, "hero", None), end_round=rules.get("end_round"))

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
        self._follow_track(rnd if rnd is not None else 1)   # before the first tower goes down
        late = rnd is not None and rnd >= 10
        if late:
            max_seconds = 150
            log.info("game starts at round %d (Fast Track?) - building the full defence first", rnd)
        if self.ex.rules.get("buy_all_upfront"):
            # no income (Deflation): the round waits for Play and the cash
            # never grows, so the build may take as long as it needs
            max_seconds = 600
        # failed spots are blocked one by one, so keep trying for a while
        # before concluding nothing can be placed (never start undefended).
        # On a late (Fast Track) start every dollar goes in before Play: Dark
        # Path Hard started round 22 with $6,025 unspent - the old loop gave up
        # after 4 idle passes whatever the cash - and lost 47 lives in seconds.
        cash = None
        while time.time() - t < max_seconds and idle < 8:
            cash = self.g.cash_stable()
            bought = self.ex.tick(cash, rnd)
            if not bought and late and cash is not None and cash > 600 and self._opening_surplus_ok():
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
        elif self._lone_opener():
            # one life and one tower: a second, cheap one from the change
            log.info("one-life opening with a single tower - adding a cheap opener beside it")
            self._place_starter(rnd, need_placed=True)
        # kept for the error play() raises when nothing went down: Tricky
        # Tracks Easy failed twice with no placement line at all, which points
        # at the cash reading rather than at the spots (108 valid offline)
        self._setup_cash = cash
        return self.ex.defended()

    def _opening_surplus_ok(self):
        """May surplus() spend between plan steps of the opening build?

        With income, yes: a Fast Track start must become a defence before
        Play, whatever the plan is waiting on. With no income (Deflation)
        the plan and its fill were designed for the whole bank, so surplus
        waits until both are exhausted. Quad Deflation (2026-11-05, case
        20261105_004356): one tick between two plan steps bought nothing,
        surplus put $21,600 into a Crossbow Master, and the fill's eight
        bombs, five snipers and three spike factories - the towers the
        build's round 47-59 margins rested on - were never afforded."""
        if not self.ex.rules.get("buy_all_upfront"):
            return True
        return self.ex.plan_exhausted()

    def _lone_opener(self):
        """True when a one-life game (CHIMPS) is about to start with a single
        non-hero tower. Winter Park CHIMPS (2026-11-05, case
        20261105_161336): the plan's $430 buccaneer left $220, its next step
        was a $280 tack, and round 6 began with the buccaneer alone. The
        damage model rated that round 2.8, yet one red slipped past the lone
        tower's single darts and the game was lost 12 seconds in. A second
        tower costs the change in hand and covers the misses of the first."""
        if not self.ex.rules.get("one_life"):
            return False
        return sum(1 for p in self.g.towers.values() if p.kind != "hero") == 1

    def _place_starter(self, rnd, tries=6, need_placed=False):
        """Only the hero is down and the plan's next tower is not affordable
        yet (Easy: hero $460 of $650, tack $260): buy the cheapest opener
        tower near the entrance so no round starts with the hero alone.
        need_placed: the defence counts as defended already (a one-life
        game's single tower, _lone_opener), so only an actual placement
        ends the search."""
        for kind in self.ex.CHEAP_OPENERS:
            if not self.ex.kind_allowed(kind):
                continue
            step = {"do": "place", "id": "starter", "kind": kind, "role": "dps", "segment": [0.05, 0.45]}
            for _ in range(tries):     # each refused spot is blocked; try the next
                with self.ex.why("starter", "opener before the plan is affordable"):
                    done = self.ex.try_step(step, self.g.cash_stable(), rnd) == "done"
                if done or (self.ex.defended() and not need_placed):
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
            raise RuntimeError(f"{NO_DEFENCE_ERROR} - refusing to start the round "
                               f"(cash read {getattr(self, '_setup_cash', None)}, "
                               f"plan: {getattr(self.ex, 'waiting', None) or 'nothing tried'})")
        self._check_no_income_build()
        self._learn_empty_map()
        self.g.go_fast(allow_start=True)
        self._in_round = True
        last_round = self.g.round()
        self._lives.update(self.g.lives())
        # the defence built before Play, as the first round snapshot
        self._journal_round(last_round, self.g.cash_stable(), setup=True)
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
            self.g.screen_lost = False      # the HUD is back: clicks are safe again
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
                if st == "game_error":
                    # the game crashed under the match: not a loss of this map
                    raise RuntimeError("the game showed its own error dialog")
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
                    self._round_lost += lost
                    self._journal_leak(last_round, lost, self._lives.confirmed)
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
                    for done in range(last_round, rnd):     # rounds completed: XP paid
                        self.tower_xp.round_end(done, list(self.g.towers.values()))
                    self._follow_ground(last_round, rnd)
                    self._follow_track(rnd)
                    # the confirmed count, not the raw read: Party Parade Hard
                    # (2026-11-05) logged "lives 1001" for twelve rounds while
                    # LivesTracker rightly held 100 - a misleading line for
                    # anyone reading game.log after a loss
                    log.info("round %d  cash %s  lives %s%s", rnd, cash, self._lives.confirmed,
                             _misread_note(lives, self._lives.confirmed))
                    status.in_game(f"round {rnd}, ${cash}, {self._lives.confirmed} lives")
                    last_round = rnd
                    self._t_round_change = now
                    self._forecast_round(rnd)
                    self._journal_round(rnd, cash, lives)
                    # once a round: a tower whose range barely reaches the
                    # track is sold, its cash goes to towers that pop bloons
                    try:
                        self.ex.sell_useless(rnd, lives_dropped=dropped)
                    except Exception:
                        log.exception("selling useless towers failed - carrying on")
                elif rnd is not None and rnd != last_round:
                    # a reading outside the expected step: adopt it only once
                    # later readings agree (RoundVotes) - a wrong round
                    # misfires threats, a stuck one ignores them
                    if self._round_votes.vote(rnd, last_round, now - self._t_round_change):
                        log.info("round tracking reset %s -> %s", last_round, rnd)
                        self._follow_ground(last_round, rnd)
                        self._follow_track(rnd)
                        last_round = rnd
                        self._t_round_change = now
                        self._forecast_round(rnd)
                        self._journal_round(rnd, cash, lives, reset=True)
                self.ex.reinforce_hold = self._reinforce_hold(last_round, dropped)
                bought = self.ex.tick(cash, last_round, lives_dropped=dropped)
                if getattr(self.g, "unconfirmed_streak", 0) >= 2 or self.g.screen_lost:
                    # Placements that leave no tower are clicks landing on
                    # something else - an end screen or a popup over the game
                    # (a missed Victory screen once took four minutes of them);
                    # screen_lost means a placement or selection found the HUD
                    # gone (Game.screen_ok): look at the screen before
                    # clicking any more.
                    self.g.unconfirmed_streak = 0
                    st = self.menus.identify()
                    if st in ("victory", "defeat") and self._real_end(st, self.g.fresh()):
                        return self._finish(st, last_round)
                    if st not in ("in_game", "unknown"):
                        outcome = self._off_screen(st)
                        if outcome:
                            return self._finish(outcome, last_round)
                        continue
                weak = self._weak_round is not None and self._weak_round == last_round
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
                    held = self._cash_held(dropped, crisis)
                    if weak and not held and now - self._t_reinforce > REINFORCE_EVERY:
                        # the coming rounds look weak: the damage model picks
                        # what the spare cash buys (reinforce.py), the plan's
                        # own steps and patience keep their place before it
                        self._t_reinforce = now
                        bought = self._reinforce(cash, last_round)
                    # reinforce is saving for a purchase that holds the weakest
                    # round: the usual spending would eat that cash
                    if not bought and not (weak and now < self._saving_until):
                        # with lives to spare a waiting plan step claims the
                        # bank only while the look-ahead is weak (plan_claim)
                        self.ex.lookahead_weak = weak
                        bought = self.ex.surplus(cash, last_round)
                if bought:
                    self._last_buy = now
                    if dropped:
                        self.stats["panic"] += 1
                    t_hud = 0  # re-read cash right away after spending
                if not bought:
                    self._park_cursor(now)
                # bananas pay only when the cursor passes over them
                if now - self._t_bananas > BANANA_EVERY:
                    self._t_bananas = now
                    got = self.g.collect_bananas()
                    if got:
                        self.stats["banana_moves"] = self.stats.get("banana_moves", 0) + got
                self._hud_update(cash, last_round)
                st = self.g.button_state()
                if st in ("play_idle", "play_run", "play_fast"):
                    self._in_round = st != "play_idle"
                    self._idle_seen = self._idle_seen or st == "play_idle"
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
            if hold and hold(rnd, cash):
                if rnd not in self._threat_holds:      # journaled once a round
                    self._threat_holds.add(rnd)
                    journal.current().event("hold", rnd=rnd, why="threat", cash=cash,
                                            waiting=getattr(self.ex, "waiting", None))
                return True
            return self._hold_for_crisis(rnd, cash)
        except Exception as e:   # the check must never stop the game from going on
            log.warning("hold_round failed: %r", e)
            return False

    def _hold_for_crisis(self, rnd, cash):
        """Keep Play waiting while the damage model expects the coming round
        (rnd, or rnd + 1 if the HUD still shows the round just played) to
        leak and the bot is still buying: reinforcing runs during the hold,
        and it ends after CRISIS_HOLD_S, or once CRISIS_HOLD_IDLE_S pass
        without a purchase. Before this the bot started every round the
        moment the last one ended - Spillway Medium (2026-11-03) went into
        round 40 with $2,329 and lost all 150 lives to its first MOAB.

        Only when the game's Auto Start is off (the Play button goes idle
        between rounds) and never under continuous sends."""
        if rnd is None or cash is None or self.ex.rules.get("continuous"):
            return False
        now = time.time()
        since = self._crisis_hold.get(rnd)
        if since is None:
            if cash < CRISIS_HOLD_MIN_CASH:
                return False
            towers = list(self.g.towers.values())
            rated = [self._crisis_margin(towers, r) for r in (rnd, rnd + 1)]
            margins = [m for m, _, _ in rated if m is not None]
            if not margins or not any(crisis for _, crisis, _ in rated):
                self._crisis_hold[rnd] = False
                return False
            self._crisis_hold[rnd] = now
            self._weak_round = rnd        # reinforce.py picks what to buy during the hold
            self._t_reinforce = 0.0
            log.warning("holding Play: the damage model rates the coming round at %.2f - "
                        "spending the $%d first", min(margins), cash)
            journal.current().event("hold", rnd=rnd, why="crisis", margin=round(min(margins), 3), cash=cash)
            return True
        if since is False:
            return False
        if now - since > CRISIS_HOLD_S or now - max(since, self._last_buy) > CRISIS_HOLD_IDLE_S:
            log.info("holding Play over after %.0f s ($%d left)", now - since, cash)
            self._crisis_hold[rnd] = False
            return False
        return True

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

    def _check_no_income_build(self):
        """Deflation: rate the finished build over the opening look-ahead
        before Play and raise WeakBuild when it would not hold. Dark Path
        Deflation (2026-11-02) spent all $40,400, its first look-ahead rated
        round 40 at 0.48 once the game had started, and it lost at round 35."""
        rules = self.ex.rules
        if not rules.get("buy_all_upfront"):
            return
        start = rules.get("start_round", 1)
        ahead = self.forecast.worst(list(self.g.towers.values()),
                                    R.lookahead_rounds(start, rules.get("end_round", 80)))
        if ahead is not None:
            log.info("no-income build before Play: the damage model rates round %d at %.2f",
                     ahead[1], ahead[0])
        if too_weak_to_start(ahead, rules):
            raise WeakBuild(*ahead)

    def _follow_ground(self, old_round, new_round):
        """Turn the remembered spots of towers on rotating ground (Geared's
        gears) by the turns made between the two rounds, so that selecting
        them clicks where they stand now (carried.CarriedTowers)."""
        if self._carried is None or old_round is None:
            return
        try:
            self._carried.round_advanced(old_round, new_round, self.g.towers)
        except Exception:
            log.exception("moving towers with the ground failed - carrying on")

    @staticmethod
    def _path_phases(model):
        """(geometry, reverse) for a map whose bloons change path by round
        (mapgeom.idle_phase_paths), else (None, False). Only models filled
        from the game's own geometry qualify: a learned track is what it is."""
        name = getattr(model, "name", None) or ""
        if not getattr(model, "geometry_bundle", None):
            return None, False
        try:
            from . import mapgeom
            reverse = name.endswith(" reverse")
            geom = mapgeom.load(name[:-len(" reverse")] if reverse else name)
            if geom and (mapgeom.idle_phase_paths(geom, 1) or mapgeom.idle_phase_paths(geom, 999)):
                return geom, reverse
        except Exception:
            log.exception("reading the map's path phases failed - every path counts as track")
        return None, False

    def _follow_track(self, rnd):
        """Paint only the paths bloons take in this round's phase and the
        next one (mapgeom.repaint_track), so towers go where bloons come now.
        Erosion Easy Primary Only was lost on round 11 with every tower
        beside paths bloons first take in rounds 37-91."""
        if self._phase_geom is None or rnd is None:
            return
        try:
            from . import mapgeom
            if mapgeom.repaint_track(self.m, self._phase_geom, rnd, self._reverse):
                self.ex.track_changed()
        except Exception:
            log.exception("repainting the track for round %s failed - carrying on", rnd)

    def _crisis_margin(self, towers, rnd):
        """(margin, crisis, leak) for round rnd: the damage model's margin,
        whether that makes it a crisis round, and the lives the model expects
        the round to cost when it is rated under 1 (forecast.lethal_leak; a
        forecast without that method - test fakes - is judged by the margin
        alone). The lives left weigh in: Pat's Pond ABR (2026-11-05) lost
        all 74 lives to round 54, rated 0.58, with $15,243 idle."""
        margin = self.forecast.margin(towers, rnd)
        lethal = getattr(self.forecast, "lethal_leak", None)
        if lethal is None:
            return margin, self.forecast.is_crisis(margin), None
        leak = lethal(towers, rnd, margin)
        lives = getattr(getattr(self, "_lives", None), "confirmed", None)
        return margin, self.forecast.is_crisis(margin, lives, leak), leak

    def _forecast_round(self, rnd):
        """Ask the damage model about the round that just started; a round it
        expects to leak becomes a crisis round (see forecast.py), and a
        weak look-ahead (this round and the next three) starts reinforcing."""
        towers = list(self.g.towers.values())
        margin, crisis, leak = self._crisis_margin(towers, rnd)
        if margin is None:
            return None
        self._margins[rnd] = margin       # for the journal's round snapshot
        if crisis:
            self._crisis_round = rnd
            cost = "" if leak is None or margin < CRISIS_MARGIN else \
                f" and expected to cost {leak:.0f} of the {self._lives.confirmed} lives left"
            log.warning("round %d: the damage model rates the defence %.2f%s - crisis round: "
                        "abilities as soon as bloons are out, no saving up", rnd, margin, cost)
        else:
            log.info("round %d: the damage model rates the defence %.2f", rnd, margin)
        end = self.ex.rules.get("end_round", 80)
        ahead = self._rate_ahead(towers, R.lookahead_rounds(rnd, end))
        self._weak_round = None
        if ahead is not None and ahead[0] < R.WEAK_MARGIN:
            self._weak_round = rnd
            log.warning("rounds %d-%d: the damage model rates round %d at %.2f - reinforcing where it "
                        "helps most", rnd, min(rnd + R.LOOKAHEAD - 1, end), ahead[1], ahead[0])
        return margin

    def _rate_ahead(self, towers, rounds):
        """(lowest margin, its round) over the look-ahead `rounds`, as
        forecast.worst. The model rates every one of them on the way to the
        lowest, so each round's margin goes to the big HUD at no extra cost
        (hudstate.py). A forecast without per-round margins (test fakes) is
        asked for the worst alone."""
        rate_each = getattr(self.forecast, "margins", None)
        if rate_each is None:
            return self.forecast.worst(towers, rounds)
        rated = rate_each(towers, rounds)
        if rated:
            hudstate.update(force=True, margins=[[r, round(m, 3)] for r, m in sorted(rated.items())],
                            weak=R.WEAK_MARGIN, crisis=CRISIS_MARGIN)
        return lowest(rated)

    def _hud_update(self, cash, rnd):
        """The match as the big HUD shows it (hudstate.py): built only when a
        write is due, at most once a second. Observe only."""
        if not hudstate.due():
            return
        try:
            towers = list(self.g.towers.values())
            plan = hudstate.plan_ahead(getattr(self.ex, "plan", None) or [], getattr(self.ex, "idx", 0))
            kinds = {p.kind for p in towers} | {s["kind"] for s in plan if s.get("kind")}
            new = kinds - set(self._hud_sizes)
            if new:      # looked up once per kind; None for a kind the game data lacks
                found = hudstate.tower_sizes(new)
                self._hud_sizes.update({k: found.get(k) for k in new})
            goal = getattr(self.ex, "save_goal", None)
            hudstate.update(round=rnd, cash=cash, lives=self._lives.confirmed,
                            waiting=getattr(self.ex, "waiting", None),
                            save_goal=list(goal) if goal else None, plan=plan,
                            towers=[[p.tid, p.kind, p.crosspath, round(p.x, 4), round(p.y, 4)] for p in towers],
                            sizes=self._hud_sizes)
        except Exception:
            log.exception("HUD state update failed - carrying on")

    # -- the game journal (journal.py): observe only ---------------------------------
    def _round_set(self):
        return getattr(self.ex, "round_set", None) or TH.set_for_mode(getattr(self.ex, "mode", None))

    def _journal_round(self, rnd, cash, lives=None, reset=False, setup=False):
        """Snapshot of the round that just started: cash, lives, the lives
        lost in the round just played, the model's margin, what the plan
        waits on and every tower with its crosspath and cash spent."""
        try:
            last_depth = self.depths[-1] if getattr(self, "depths", None) else None
            # `lives` is the tracker's confirmed count; a raw HUD read that
            # disagrees with it (an OCR misread such as 1001 for 100) is kept
            # beside it as `lives_read`, so the journal never shows a misread
            # as the game's state
            confirmed = self._lives.confirmed
            fields = dict(rnd=rnd, cash=cash, lives=lives if confirmed is None else confirmed,
                          lives_lost_round=self._round_lost, margin=self._margins.get(rnd),
                          crisis=self._in_crisis(rnd),
                          depth=last_depth.get("deepest") if last_depth else None,
                          waiting=getattr(self.ex, "waiting", None),
                          towers=[[p.tid, p.kind, p.crosspath, p.spent] for p in self.g.towers.values()])
            if lives is not None and confirmed is not None and lives != confirmed:
                fields["lives_read"] = lives
            if reset:
                fields["reset"] = True
            if setup:
                fields["setup"] = True
            self._round_lost = 0
            journal.current().round(**fields)
        except Exception:
            log.exception("journal round snapshot failed - carrying on")

    def _journal_leak(self, rnd, lost, lives_after, inferred=False):
        """A leak, tied to what the round brings: its bloon groups with their
        share of the round's RBE, the properties nothing on the map pops,
        and the blimp check of a blimp round. Each piece may fail alone."""
        fields = {"rnd": rnd, "lost": lost, "lives_after": lives_after,
                  "margin": self._margins.get(rnd), "inferred": inferred}
        self._leak_rounds.add(rnd)
        if rnd is not None:
            rset = self._round_set()
            try:
                groups = []
                for g in TH.round_groups(rset, rnd):
                    count = g.get("count", 1)
                    fortified = bool(g.get("fortified"))
                    groups.append({"bloon": g["bloon"], "count": count, "camo": bool(g.get("camo")),
                                   "regrow": bool(g.get("regrow")), "fortified": fortified,
                                   "rbe": count * TH.rbe(g["bloon"], fortified),
                                   "blimp_hp": count * TH.blimp_hp(g["bloon"], fortified)})
                total = sum(g["rbe"] for g in groups) or 1
                for g in groups:
                    g["share"] = round(g["rbe"] / total, 3)
                fields["groups"] = groups
            except Exception as e:
                fields["groups_error"] = repr(e)
            try:
                fields["uncovered"] = sorted(TH.sig_name(s) for s in TH.round_signatures(rset, rnd)
                                             if not self.ex._covers(s)[0])
            except Exception as e:
                fields["uncovered_error"] = repr(e)
            try:
                load = TH.round_blimp_load(rset, rnd, double_hp=bool(self.ex.rules.get("tough_moabs")))
                if load:
                    fields["blimp_ratio"] = round(self.ex.blimp_ratio(load), 3)
            except Exception as e:
                fields["blimp_error"] = repr(e)
        try:
            journal.current().leak(**fields)
        except Exception:
            log.exception("journal leak failed - carrying on")

    def _cash_held(self, dropped, crisis):
        """Is the cash the executor is saving (Executor.saving_for_threat: a
        threat's answer or the plan's blimp damage) off limits to
        reinforcing? Such cash is not spare - Spillway ABR (2026-11-04): a
        $430 ninja for round 49 left round 40's Maim MOAB unaffordable -
        unless lives are falling now, or the round being played is a crisis
        round (_in_crisis: rated under forecast.CRISIS_MARGIN at its start).

        In a crisis round the game is at stake before the held answer is
        needed. The executor holds for a round at least this one, and what
        it holds for this very round can no longer be bought before the
        bloons: Ancient Portal Impoppable (2026-11-05), round 94, "idle with
        $17562: saving for blimp damage before round 94" while round 94 was
        being played, rated 0.45, and lost. _hold_for_crisis had held Play
        for that round promising to spend the cash first, so reinforce is
        let at the cash. The trade this accepts: the executor does not say
        which round it holds for, so a hold for the next round's answer
        (held whole by Executor._hold_for when due within FAR_ROUNDS) is
        let go too, and a purchase for this round can eat it. It is bounded
        because reinforce judges a purchase in a crisis on the lowest of
        this round, the next one and the weakest ahead (reinforce.lift), so
        the next round's blimps weigh in the choice, and buys one purchase
        per look. Spillway's $430 ninja for round 49 was bought in a round
        that held, which this still forbids. surplus() keeps off either way:
        the executor checks saving_for_threat itself. Outside a crisis a
        hold for a round two or three away stays whole (Spillway ABR
        again)."""
        return bool(getattr(self.ex, "saving_for_threat", False)) and not dropped and not crisis

    def _reinforce_hold(self, rnd, dropped):
        """The cash the plan's own steps must leave alone this tick: the cost
        of the purchase reinforce is saving for (Executor.save_goal, set by
        reinforce.buy_best on 'save'), else 0.

        The hold lasts until reinforce's next look answers something else
        (each look rewrites save_goal), so the gap between two looks is
        covered too. It ends early when the look-ahead is no longer weak,
        when the saved-for round has come (saving for it is over), when lives
        are falling, or when the round being played is itself a crisis round
        (_in_crisis) - then the plan may spend as before."""
        goal = getattr(self.ex, "save_goal", None)
        if not goal or rnd is None or dropped or self._in_crisis(rnd):
            return 0
        cost, worst = goal
        if self._weak_round != rnd or rnd >= worst:
            return 0
        return cost

    def _reinforce(self, cash, rnd):
        """One model-chosen purchase (reinforce.py). True when one was bought;
        the weak state ends when nothing affordable helps any more."""
        try:
            r = R.buy_best(self.ex, self.forecast, cash, rnd, self.ex.rules.get("end_round", 80),
                           lives=self._lives.confirmed)
        except Exception:
            log.exception("reinforcing failed - back to the usual spending")
            self._weak_round = None
            return False
        if r == "safe":
            self._weak_round = None   # the look-ahead holds: surplus as usual
        elif r in ("wait", "save"):
            # nothing the cash buys helps yet: look again once more cash came in
            self._t_reinforce = time.time() + REINFORCE_WAIT - REINFORCE_EVERY
        # 'save': surplus() must not spend the cash either, until the next look
        self._saving_until = self._t_reinforce + REINFORCE_EVERY if r == "save" else 0.0
        return r == "bought"

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
    MENU_SCREENS = ("main_menu", "map_select", "difficulty", "mode_select", "monkeys_menu", "title", "legends")
    # Unknown screens in a row before every UNKNOWN_BACK_EVERY-th click goes
    # to the top-left back arrow instead of the centre: a full-screen
    # announcement continues on a click anywhere, but a menu page only
    # leaves by its back arrow (in a match that corner is the lives counter,
    # where a click does nothing).
    UNKNOWN_BACK_EVERY = 5
    BACK_ARROW = (0.044, 0.055)

    def _off_screen(self, st=None):
        st = st or self.menus.identify()
        log.info("off game screen: %s", st)
        if st == "victory":
            return st
        if st == "defeat":
            # a defeat needs evidence: lives near zero (the Legends page once
            # read as "defeat" with all 200 lives - a game that had been WON).
            # The card itself is evidence too: in Double HP MOABs one leaked
            # MOAB takes 75 lives at once, so the counter never neared zero
            # (Cargo, 2026-11-03).
            lives = self._lives.median()
            if lives is None or lives <= 20 or self._defeat_card():
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
        elif st in ("collection_event", "reward_cards", "insta_reward"):
            # free reward screens: Alpine Run Impoppable's round-100 win put an
            # "INSTA MONKEY!" card up, and with no case here the loop read it
            # 400 times in 8 minutes without a click (2026-11-04 11:17)
            self.menus.handle_collection_event()
        elif st == "upgrade_tree":
            self.g.leave_tree()
        elif st == "pause":
            self.menus.click_word("continue")
        elif st == "in_game":
            # identify() only checks the Play button's shape; Game.in_game also
            # wants it lit. Shape there but dimmed means a popup covers the
            # match: close it if it has a plain button (never a paid one).
            if not self.g.in_game():
                self.menus.dismiss_popup()
            return None
        else:
            if not self.menus.dismiss_popup():
                # full-screen announcements (new hero, rewards) continue on click
                self._unknown = getattr(self, "_unknown", 0) + 1
                from .menus import page_forbidden
                if self._unknown >= 3 and not page_forbidden(self.menus.words):
                    if self._unknown % self.UNKNOWN_BACK_EVERY == 0:
                        log.info("unknown screen x%d - trying the back arrow", self._unknown)
                        self.menus.inp.click(*self.BACK_ARROW)
                    else:
                        log.info("unknown screen x%d - clicking to continue", self._unknown)
                        self.menus.inp.click(0.5, 0.5)
                time.sleep(0.8)
        return None

    def _park_point(self):
        """Screen spot over the busiest stretch of track: the track cell with
        the most track around it (a bend or a stretch where lanes meet), so
        a tower aiming at the cursor fires into the thick of the bloons."""
        if self._park is None:
            import cv2
            import numpy as np
            heat = getattr(self.m, "heat", None)
            if heat is None or not (heat > 0).any():
                return None
            track = (heat > 0).astype(np.float32)
            dens = cv2.boxFilter(track, -1, (PARK_WINDOW, PARK_WINDOW))
            dens[track == 0] = 0
            y, x = np.unravel_index(int(np.argmax(dens)), dens.shape)
            self._park = self.m.cell_to_frac(int(x), int(y))
        return self._park

    def _park_cursor(self, now):
        """Rest the cursor on the busiest track while something follows it
        (a Dartling Gunner, or a heli whose targeting is not set yet)."""
        if now - self._t_park < PARK_EVERY:
            return
        self._t_park = now
        towers = self.g.towers.values()
        if not any(p.kind == "dartling" or (p.kind == "heli" and getattr(p, "aim", None) not in ("lock", "pursuit"))
                   for p in towers):
            return
        spot = self._park_point()
        if spot is None:
            return
        import win32api
        x, y = self.g.s.to_px(*spot) if hasattr(self.g, "s") else (None, None)
        if x is not None:
            cx, cy = win32api.GetCursorPos()
            if abs(cx - x) <= PARK_SLACK and abs(cy - y) <= PARK_SLACK:
                return                        # already resting there
        self.g.inp.move(*spot, fast=True)

    DEFEAT_READS = 15    # this many defeat screens in a row count as a defeat, whatever the lives read

    def _defeat_card(self):
        """True when the last OCR read shows the defeat card itself: "Bloons
        Leaked", or "Defeat" next to its Restart / Review Map buttons. These
        appear nowhere else. On 2026-10-27 the lives counter behind the card
        read "1" and the bot ignored a real defeat for ten minutes."""
        words = {norm(w.text) for w in self.menus.words}
        return any("bloonsleaked" in w for w in words) or (
            any("defeat" in w for w in words) and any(k in w for w in words for k in ("restart", "reviewmap")))

    def _real_end(self, st, f):
        """A defeat needs the lives counter to agree: a word like 'defeat' can
        show up in tower/upgrade panels and once made the bot quit three games
        it was winning at full lives."""
        if st != "defeat":
            self._defeat_reads = 0
            return True
        self._defeat_reads = getattr(self, "_defeat_reads", 0) + 1
        if self._defeat_card() or self._defeat_reads >= self.DEFEAT_READS:
            return True
        lives = self.g.hud.lives(f) if f is not None else None
        known = self._lives.median()
        if lives and lives > 0 and (known is None or known > 0):
            hits = [w.text for w in self.menus.words
                    if any(k in norm(w.text) for k in ("defeat", "gameover", "bloonsleaked", "youlost"))]
            log.warning("ignoring 'defeat' screen: lives still %s (matched %s)", lives, hits)
            if self._defeat_reads == 1:           # one picture per false alarm, not one every 2 s
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
        if outcome == "victory":
            self.tower_xp.round_end(rnd, list(self.g.towers.values()))   # the last round paid too
        self.stats["tower_xp"] = self.tower_xp.rounded()
        # plan steps given up because the game refused every spot tried: the
        # runner notes a lost game with any as placement trouble on the map
        self.stats["steps_given_up"] = len(getattr(self.ex, "dead_steps", ()))
        if self.depths:
            # the deepest point bloons reached in any round (bloonwatch.py)
            self.stats["bloon_depth"] = max(s["deepest"] for s in self.depths)
        self.stats.update(outcome=outcome, round=rnd, minutes=(time.time() - self.stats["start"]) / 60)
        if not self._idle_seen and self.stats.get("rounds", 0) >= AUTO_START_ROUNDS                 and not self.ex.rules.get("continuous"):
            log.warning("the Play button was never idle in %d rounds: BTD6's Auto Start setting looks "
                        "ON, so the bot cannot hold a round to buy - turn it off in the game's settings",
                        self.stats["rounds"])
            self.stats["auto_start"] = True
        cause = self._journal_end(outcome, rnd)
        hudstate.end_game()
        if cause:
            log.info("game over: %s (cause: %s - %s)", self.stats, cause["category"], cause["evidence"])
        else:
            log.info("game over: %s", self.stats)
        return self.stats

    def _journal_end(self, outcome, rnd):
        """Write game_end; for a game not won, with its cause of death
        (journal.cause_of_death), returned for the log. A one-life game
        dies before the lives tracker can confirm the drop (a single read
        of 0, then the Defeat card), so a defeat without a leak in the
        journal for its round gets one, inferred, losing the last lives
        the tracker trusted."""
        try:
            if outcome == "defeat" and rnd not in self._leak_rounds:
                lives = self._lives.confirmed
                if lives is None:
                    lives = (getattr(self.ex, "rules", None) or {}).get("lives")
                self._journal_leak(rnd, lives, 0, inferred=True)
            jr = journal.current()
            cause = None if outcome == "victory" else journal.cause_of_death(jr.events, rnd, self.stats)
            jr.end(outcome=outcome, round=rnd, stats=self.stats, cause=cause)
            return cause
        except Exception:
            log.exception("journal game end failed - carrying on")
            return None
