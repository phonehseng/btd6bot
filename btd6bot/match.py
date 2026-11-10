"""Playing one game from the first placement to the victory/defeat screen."""
import logging
import time

from . import clicktime as CT
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
PLAN_YIELD_DEPTH = 0.9  # bloons this far along the route last round: a plan_first step may yield (_plan_lets_reinforce)
REINFORCE_WAIT = 8.0    # ... and after a look that found nothing affordable to help
WATCH_EVERY = 0.2       # seconds between looks of the bloon watch during a round
EMPTY_LOOK_GAP = 0.1    # seconds between looks at the empty map before round 1
# Play waits while the damage model expects the coming round to leak and
# purchases are still being made (Match._hold_for_crisis): the break between
# rounds is free time to spend in.
CRISIS_HOLD_S = 20.0       # longest wait per round
CRISIS_HOLD_IDLE_S = 4.0   # ... ended early once this long passes without a purchase
CRISIS_HOLD_MIN_CASH = 300  # less than this buys nothing that matters
# The game lights the Play button again as soon as a round's last bloon has
# been sent, while its bloons are still on the track; pressing it sends the
# next round on top of them. With one life, Play waits until the bloon watch
# sees the track empty (Match._hold_for_clear).
CLEAR_LOOKS = 4            # looks in a row with no bloon on the route = clear
CLEAR_HOLD_MAX_S = 25.0    # longest wait per round (a watch that never clears)
# Rounds in a row whose wait ran to CLEAR_HOLD_MAX_S before the watch is taken
# to misread this map and the waits stop for the rest of the game.
CLEAR_CAPPED_ROUNDS = 2
# A game past its time limit is still played on while rounds keep coming: it
# ends as a timeout only when no new round has started for this long, or at
# GAME_HARD_LIMIT_FACTOR times the limit.
ROUND_STALL_S = 600.0
GAME_HARD_LIMIT_FACTOR = 3.0
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
# One pass of the play loop normally takes well under a second; a run of
# purchases or a reinforce look can take several. A pass that took longer
# than this means the loop was held up (a starved PC, a blocking call), and
# the game may have ended meanwhile: Spring Spring CHIMPS (2026-11-08) was
# lost at 22:30:28, while the PC was busy with tools/check.py's 16 test
# processes, and the bot logged nothing until "off game screen: defeat" at
# 22:32:25. After such a pass the loop looks for an end screen first.
LOOP_STALL_S = 15.0
# the in-round Powers run (Match._in_round_powers_due): seconds after a round began
IN_ROUND_POWERS_AFTER = 2.0
IN_ROUND_POWERS_UNTIL = 8.0


class LoopBeat:
    """The play loop's heartbeat: when it last passed a checkpoint and which.

    Match.play marks each phase of a pass (_mark); bot.py's stack-snapshot
    thread asks stall_report() every few seconds and, when the loop has
    been stuck in one phase for long, saves where every thread was. The
    minute-by-minute logs/stacks.txt is overwritten, so the snapshot taken
    during a two-minute stall was gone by the time anyone looked."""
    t = 0.0           # time.time() of the last checkpoint; 0 = no game being played
    phase = ""
    reported = 0.0    # the checkpoint time a stall was last reported for

    @classmethod
    def mark(cls, phase, now=None):
        cls.t = time.time() if now is None else now
        cls.phase = phase

    @classmethod
    def stop(cls):
        cls.t = 0.0
        cls.phase = ""

    @classmethod
    def stall_report(cls, now=None, limit=LOOP_STALL_S):
        """'stuck N s in <phase>' once per stall longer than `limit`, else None."""
        now = time.time() if now is None else now
        if not cls.t or now - cls.t <= limit or cls.reported == cls.t:
            return None
        cls.reported = cls.t
        return f"stuck {now - cls.t:.0f} s in {cls.phase or '?'}"


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
    * A vote never lifts the count above the starting lives, unless the
      defence can gain lives (`can_gain`, set from the towers by the match:
      lives_gainers). The vote exists to undo a wrong LOW count (15 for
      150), which the start bounds. Last Resort Medium (2026-11-10): lives
      fell 150 -> 21 in rounds 15-16 and the OCR then read the 21 as "218"
      (a phantom digit beside the shield badge) four times in a row. The
      vote took 218, the bot thought it was safe and lost three rounds
      later. Small true gains still pass the RISE_LIMIT check either way.
    * With `can_gain` the max_lives ceiling is lifted too: Spirit of the
      Forest, Support Chinook, Energizer, Benjamin and Healthy Bananas farms
      take lives far past the start (the 1000-lives achievement), and a
      count stuck below the truth would hide every later leak.
    """
    RISE_LIMIT = 50
    RISE_VOTES = 4

    def __init__(self, start_lives=None, fixed=False):
        self.confirmed = None
        self.reads = []                       # last 5 accepted reads
        self.start_lives = start_lives
        self.can_gain = False                 # the defence can add lives (see lives_gainers)
        if start_lives and fixed:
            self.max_lives = start_lives
        else:
            self.max_lives = 2 * start_lives + 25 if start_lives else None
        self._cand, self._votes = None, 0     # an upward correction being voted on

    def median(self):
        return sorted(self.reads)[len(self.reads) // 2] if self.reads else None

    def update(self, read):
        """Feed one read (None = unreadable). Returns the lives lost (0 if none)."""
        if read is not None and self.max_lives and read > self.max_lives and not self.can_gain:
            read = None    # impossible for this mode, even as the very first read
        read = self._drop_phantom_digit(read)
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

    def _drop_phantom_digit(self, read):
        """A read that can only be the true count with a phantom digit on the
        end becomes its leading digits.

        Refusing such a read (the vote's start cap) keeps the count from
        jumping up, but it also keeps the count at its last value, so the leak
        behind it is never seen: Last Resort Medium (2026-11-10) read 21 lives
        as "218" and Last Resort Magic Only read 13 as "131"; both counts
        stayed at the pre-leak value and crisis spending never began.

        The read is rewritten only when all of these hold, so a true count is
        never touched: nothing in the defence can gain lives; the read is above
        the starting lives (impossible then) and far above the confirmed count
        (a jump the rise check would ignore anyway); and its leading digits
        (read // 10) are at or below the confirmed count, i.e. they describe a
        leak, not a gain. A wrong low first read (15 for 150) is unaffected:
        the true 150 is not above the start.

        The OCR also adds a phantom LEADING 1 at the heart's edge (see the
        class docstring): 50 lives read as "150" must stay 50, not become a
        35-life leak. So when the digits after a leading 1 equal the confirmed
        count (within 2), that reading wins."""
        if (read is None or self.can_gain or not self.start_lives
                or self.confirmed is None):
            return read
        if not (read > self.start_lives and read > self.confirmed + self.RISE_LIMIT):
            return read
        digits = str(read)
        if digits.startswith("1") and len(digits) > 1 and abs(int(digits[1:]) - self.confirmed) <= 2:
            log.debug("lives read %d taken as %s (phantom leading 1)", read, digits[1:])
            return int(digits[1:])
        if read // 10 <= self.confirmed:
            log.debug("lives read %d taken as %d (phantom trailing digit)", read, read // 10)
            return read // 10
        return read

    def _vote_rise(self, read):
        """A read far above the confirmed count. True once RISE_VOTES reads in
        a row agree (within 2): the count then restarts from it. False while
        it is still only a suspected misread, and always False above the
        starting lives (see the class docstring)."""
        if self.start_lives and read > self.start_lives and not self.can_gain:
            self._cand, self._votes = None, 0
            return False
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


def lives_gainers(towers, hero=None):
    """True when the defence can add lives, so a count above the starting
    lives is possible (LivesTracker.can_gain). From the bot's achievement
    notes (Reach 1000 lives): Druid middle path 4+ (Jungle's Bounty, Spirit
    of the Forest), Heli middle path 4+ (Support Chinook), Sub top path 5
    (Energizer), any Banana Farm (Healthy Bananas knowledge) and Benjamin."""
    if str(hero or "").lower() == "benjamin":
        return True
    for p in towers:
        kind, tiers = getattr(p, "kind", ""), list(getattr(p, "tiers", None) or (0, 0, 0))
        if kind in ("druid", "heli") and tiers[1] >= 4:
            return True
        if kind == "sub" and tiers[0] >= 5:
            return True
        if kind == "farm":
            return True
    return False


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

    Under continuous sends (Apopalypse: the next round starts while the
    last one is still on the track) rounds are much shorter: bot.log of
    2026-11-06 shows a median of 2.5-3 s per round from round 45 on, often
    less. With the 3 s floor the catch-up readings looked implausible, and
    nearly every Apopalypse game lost track late ("round tracking reset
    49 -> 59"). Party Parade Apopalypse was lost at round 58 while the bot
    still believed round 49: no crisis rounds or abilities for the real
    rounds. Those games use CONTINUOUS_MIN_ROUND_SECONDS instead.
    """
    MAX_STEP = 2               # rounds the game may move on between two readings
    MIN_ROUND_SECONDS = 3.0    # no round is over faster than this, even on fast forward
    CONTINUOUS_MIN_ROUND_SECONDS = 1.0   # the same under continuous sends (Apopalypse)
    PLAUSIBLE_VOTES = 3        # forward jumps the elapsed time explains
    SMALL_VOTES = 4            # other changes of up to 3 rounds
    BIG_VOTES = 15             # anything else (a misread like '11' -> '711')

    def __init__(self, continuous=False):
        """continuous: the mode sends rounds without breaks (strategy rules
        'continuous'), so rounds can pass faster than MIN_ROUND_SECONDS."""
        if continuous:
            # an instance attribute shadows the class floor for this game only
            self.MIN_ROUND_SECONDS = self.CONTINUOUS_MIN_ROUND_SECONDS
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
    def __init__(self, game, menus, model, executor, account=None, on_tower_choice=None, extras=None):
        self.g = game
        # powers.InGameExtras (Powers / Instas for achievements) or None
        self.extras = extras
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
        self._round_votes = RoundVotes(continuous=bool(rules.get("continuous")))
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
        # rounds the map's melts come before the trigger rounds in this game
        # (learned from the first early melt, _melt_check)
        self._ground_lead = 0
        self.ex.melt_check = self._melt_check
        self._t_round_change = time.time()   # when the tracked round last changed
        self._last_buy = time.time()
        self._last_wait_log = 0.0
        self._t_bananas = 0.0      # last pass over the farms' bananas
        self._t_park = 0.0         # last cursor park (PARK_EVERY)
        self._park = None          # where the cursor rests: the busiest track (screen fractions)
        self.abil = AbilityPlanner(getattr(game, "hero", None), getattr(executor, "rules", None))
        # a plan's `do: ability` step takes its hotkey guesses and the hero's
        # placement round from the same planner (Executor._try_ability)
        executor.abil = self.abil
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
        self._clear_hold = {}       # round -> [time Play started waiting, empty looks], or False
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
            self._setup_screen_check()
            cash = self.g.cash_stable()
            # one life and one tower so far: the plan may not spend the
            # money a second tower needs (_opener_reserve)
            plan_cash = cash if cash is None else max(0, cash - self._opener_reserve())
            self.ex.play_running = False     # before Play: platforms as in the round before
            self._follow_platforms(rnd)
            bought = self.ex.tick(plan_cash, rnd)
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
        self._setup_screen_check()
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

    def _setup_screen_check(self):
        """During the opening build: once a placement found the HUD gone
        (Game.screen_ok set screen_lost), look at the screen, close a popup
        over the match and allow clicks again when the HUD is back.

        The match loop does this for every pass (play), but the opening
        build ran before it: on Sunken Columns Double HP (2026-11-09 07:53)
        a stray click had opened an obstacle's "Remove for $1,000" box
        before the first placement, every plan step then waited "(screen)"
        for 20 s, and the game was refused with "no defence could be
        placed". Menus.dismiss_popup closes such a box with its red X and
        never confirms a purchase."""
        if not self.g.screen_lost:
            return
        menus = getattr(self, "menus", None)
        if menus is None:
            return
        st = menus.identify()
        log.info("opening build: the HUD is covered (%s) - looking for a popup", st)
        if st in ("in_game", "unknown"):
            menus.dismiss_popup()
        elif st not in ("victory", "defeat", *self.MENU_SCREENS):
            self._off_screen(st)        # level up, reward screens, pause ...
        if self.g.in_game():
            log.info("opening build: the HUD is back - placing again")
            self.g.screen_lost = False

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
        tower costs the change in hand and covers the misses of the first.

        A build that writes `starter: none` opts out (_no_starter): on its map
        no legal cell lets the cheap second tower reach the track, and the
        change is worth more as the opener's next upgrade."""
        if not self.ex.rules.get("one_life") or self._no_starter():
            return False
        return sum(1 for p in self.g.towers.values() if p.kind != "hero") == 1

    def _no_starter(self):
        """True when the build says `starter: none`: no second tower beside
        a lone opener, and no cash kept back for one.

        Sulfur Springs CHIMPS (2026-11-07, games 18:43 and 19:57): the
        starter dart stood at (0.473, 0.871) and at (0.345, 0.078), and the
        recordings show it never threw a dart - the legal cells near the
        track's first quarter are cliffs out of a dart's reach. Both games
        were lost in round 9 to its 30 greens with the boat at 1-0-0, $10
        short of Double Shot (2-0-0, $460). Without the $215 starter the
        boat has Faster Shooting from round 7's start and Double Shot from
        round 9's start."""
        strat = getattr(self.ex, "strat", None)
        return isinstance(strat, dict) and strat.get("starter") == "none"

    def _opener_reserve(self):
        """Cash the plan must leave untouched before the first Play of a
        one-life game while a single non-hero tower stands: the price of the
        cheapest opener this game allows, so _place_starter can still add a
        second tower beside the first (_lone_opener).

        Alpine Run CHIMPS (2026-11-06, journal 20261106_101656): the plan put
        $635 of the $650 start into one tack (place, 0-1-0, 0-2-0). The
        second-tower check came after that and found $15, so round 6 started
        with the tack alone and a bloon slipped between its eight tack lines
        30 seconds in. With this reserve the tack stops at 0-1-0 and a dart
        goes down next to it; the plan's 0-2-0 follows from round 6's pops.
        0 when the game has lives to spare or the tower count is not one."""
        if not self._lone_opener():
            return 0
        spec = self._starter_spec()
        if spec is not None:
            # the build names its starter: keep back that tower's price
            price = self.g.price(spec["kind"])
            if price is not None and price != float("inf"):
                return price
        prices = [self.g.price(k) for k in self.ex.CHEAP_OPENERS if self.ex.kind_allowed(k)]
        prices = [p for p in prices if p is not None and p != float("inf")]
        return min(prices) if prices else 0

    def _starter_spec(self):
        """The build's own starter tower, `starter: {kind: dart, at: [fx, fy]}`
        at the top of a strategy file, or None (then the cheapest allowed
        opener goes on the entrance part of the track, as before).

        Sulfur Springs CHIMPS (2026-11-07 18:43): the same build that held
        rounds 6-39 at 16:01 lost round 9 because the starter dart, refused
        at (0.526, 0.181), went to (0.473, 0.871), where it popped almost
        nothing; every lost boat opening had such a starter. A build can now
        put it where it covers what the opener cannot. A kind the game does
        not allow is ignored."""
        strat = getattr(self.ex, "strat", None)
        spec = strat.get("starter") if isinstance(strat, dict) else None
        if not isinstance(spec, dict) or spec.get("kind") not in T.TOWERS:
            return None
        if not self.ex.kind_allowed(spec["kind"]):
            return None
        return spec

    def _starter_steps(self):
        """The place steps _place_starter tries, in order: the build's own
        starter at its spot (a refused spot moves a few cells, then anywhere:
        Executor's `at` fallback), then the cheapest allowed openers on the
        entrance part of the track."""
        steps = []
        spec = self._starter_spec()
        if spec is not None:
            step = {"do": "place", "id": "starter", "kind": spec["kind"], "role": "dps"}
            if spec.get("at"):
                step["at"] = [float(v) for v in spec["at"]]
            else:
                step["segment"] = [0.05, 0.45]
            steps.append(step)
        for kind in self.ex.CHEAP_OPENERS:
            if self.ex.kind_allowed(kind) and not (spec is not None and kind == spec["kind"]):
                steps.append({"do": "place", "id": "starter", "kind": kind, "role": "dps",
                              "segment": [0.05, 0.45]})
        return steps

    def _place_starter(self, rnd, tries=6, need_placed=False):
        """Only the hero is down and the plan's next tower is not affordable
        yet (Easy: hero $460 of $650, tack $260): buy the cheapest opener
        tower near the entrance so no round starts with the hero alone.
        need_placed: the defence counts as defended already (a one-life
        game's single tower, _lone_opener), so only an actual placement
        ends the search."""
        for step in self._starter_steps():
            kind = step["kind"]
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
        self._achievement_extras()
        self.g.go_fast(allow_start=True)
        self._in_round = True
        last_round = self.g.round()
        self._first_round = last_round          # the in-round Powers wait for the round after it
        self._lives.update(self.g.lives())
        # the defence built before Play, as the first round snapshot
        self._journal_round(last_round, self.g.cash_stable(), setup=True)
        self.tracer.start_round()
        t_hud = t_ability = 0.0
        cash = None
        t_pass = time.time()
        try:
            return self._play_loop(max_minutes, last_round, t_hud, t_ability, cash, t_pass)
        finally:
            LoopBeat.stop()

    def _mark(self, phase, now=None):
        """Note which phase of the play loop starts now (LoopBeat), and keep
        the slowest phase since the last _take_slowest as (name, seconds)."""
        now = time.time() if now is None else now
        prev, t0 = getattr(self, "_phase", ""), getattr(self, "_t_phase", now)
        if prev and now - t0 > getattr(self, "_slowest", ("", 0.0))[1]:
            self._slowest = (prev, now - t0)
        self._phase, self._t_phase = phase, now
        LoopBeat.mark(phase, now)

    def _take_slowest(self):
        """The slowest phase marked since the last call, and start afresh."""
        slow = getattr(self, "_slowest", ("", 0.0))
        self._slowest = ("", 0.0)
        return slow

    def _after_stall(self, away, slowest, f):
        """The last pass of the play loop took `away` seconds, most of them
        in `slowest` (name, seconds): look at the screen before anything
        else - the game may have ended meanwhile. Returns the outcome when
        it has, else None."""
        name, secs = slowest
        log.warning("match loop was held up %.0f s (%.0f s of it in %s) - looking for an end screen",
                    away, secs, name or "?")
        st = self.menus.identify()
        if st in ("victory", "defeat") and self._real_end(st, f):
            return st
        if st not in ("in_game", "unknown"):
            return self._off_screen(st)
        return None

    def _play_loop(self, max_minutes, last_round, t_hud, t_ability, cash, t_pass):
        while not self._out_of_time(max_minutes):
            self._mark("screen grab")
            f = self.g.fresh()
            self._mark("pass start")
            slowest = self._take_slowest()
            away, t_pass = time.time() - t_pass, time.time()
            if away > LOOP_STALL_S and self.g.in_game(f):
                outcome = self._after_stall(away, slowest, f)
                if outcome:
                    return self._finish(outcome, last_round)
                if self.g.towers:    # abilities first: they may be due by now
                    t_ability = time.time()
                    self._abilities(last_round)
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
                self._mark("end screen check")
                st = self.menus.identify()
                if st in ("victory", "defeat") and self._real_end(st, f):
                    return self._finish(st, last_round)
            if self._frozen(f, now):
                # a modal popup pauses the game while the HUD stays visible
                self._mark("frozen screen")
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
                self._mark("bloon watch")
                self._watch_look(f, now)
            dropped = False
            if now - t_hud > 0.35:
                t_hud = now
                self._mark("HUD read")
                cash = self.g.hud.cash(f)
                rnd = self.g.hud.round(f)
                lives = self.g.hud.lives(f)
                if (cash is None or lives is None) and self.g.close_panels():
                    continue
                # leaks, misreads and upward corrections: see LivesTracker
                self._lives.can_gain = lives_gainers(self.g.towers.values(), getattr(self.g, "hero", None))
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
                        self._mark("abilities")
                        self._abilities(last_round, dropped=True)
                self._prev_lives_read = lives
                # rounds only move forward, one or two at a time
                if rnd is not None and last_round is not None and last_round < rnd <= last_round + 2:
                    self.tracer.end_round()
                    self.tracer.start_round()
                    self.stats["rounds"] += rnd - last_round
                    self._mark("round change")
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
                    self._note_round_length(now - self._t_round_change, rnd - last_round)
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
                self._mark("plan tick")
                self.ex.play_running = self._in_round
                self._follow_platforms(last_round)
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
                    # a plan_first build's plan owns the cash (Executor.plan_first),
                    # unless its waiting step cannot come before a near round
                    # rated a crisis (Executor.plan_first_yields)
                    if weak and not self._plan_lets_reinforce(cash, last_round):
                        weak = False
                    if weak and not held and now - self._t_reinforce > REINFORCE_EVERY:
                        # the coming rounds look weak: the damage model picks
                        # what the spare cash buys (reinforce.py), the plan's
                        # own steps and patience keep their place before it
                        self._t_reinforce = now
                        self._mark("reinforce")
                        bought = self._reinforce(cash, last_round)
                    # reinforce is saving for a purchase that holds the weakest
                    # round: the usual spending would eat that cash
                    if not bought and not (weak and now < self._saving_until):
                        # with lives to spare a waiting plan step claims the
                        # bank only while the look-ahead is weak (plan_claim)
                        self.ex.lookahead_weak = weak
                        self._mark("surplus")
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
                    self._mark("bananas")
                    got = self.g.collect_bananas()
                    if got:
                        self.stats["banana_moves"] = self.stats.get("banana_moves", 0) + got
                self._mark("Play button")
                self._hud_update(cash, last_round)
                st = self.g.button_state()
                if st in ("play_idle", "play_run", "play_fast"):
                    self._in_round = st != "play_idle"
                    self._idle_seen = self._idle_seen or st == "play_idle"
                if st == "play_run":
                    self.g.go_fast(allow_start=False)
                elif st == "play_idle" and self.ex.defended() and not self._hold_round(last_round, cash) \
                        and not self._hold_for_clear(last_round, f, now):
                    self.g.go_fast(allow_start=True)
                    self._in_round = True
                if self._in_round_powers_due(now, last_round, dropped):
                    # once a game; the panel covers the tower list for a few seconds
                    self._mark("achievement powers")
                    self._achievement_extras(phase="round")
                    t_hud = 0               # re-read the HUD right after
            if self.g.towers and now - t_ability > 1.0:
                t_ability = now
                self._mark("abilities")
                self._abilities(last_round)
            time.sleep(0.02)
        return self._finish("timeout", last_round)

    # rounds longer than this are not the game's pace (a pause, a popup,
    # a round the bot held back) and are left out of the measured length
    ROUND_LENGTH_MAX_S = 30.0

    def _note_round_length(self, seconds, rounds):
        """Under a click budget (clicktime.time_limited) keep the measured
        length of a round in ex.round_seconds - a running mean of the time
        between round changes, per round - for the seconds a purchase has
        before the round it is for (clicktime.time_left)."""
        if not CT.time_limited(self.ex) or rounds <= 0:
            return
        per = seconds / rounds
        if not 0.5 <= per <= self.ROUND_LENGTH_MAX_S:
            return
        old = getattr(self.ex, "round_seconds", None)
        self.ex.round_seconds = per if not old else (1 - CT.LEARN) * old + CT.LEARN * per

    def _in_round_powers_due(self, now, rnd, dropped):
        """Time for the once-a-game Powers run (powers.InGameExtras, phase
        "round")? The instant Powers are greyed out before round 1, so they
        are used in a running round: the second round this game plays (the
        first one's bloons have shown the defence holds), IN_ROUND_POWERS_AFTER
        seconds after it began (its bloons are on screen) and before
        IN_ROUND_POWERS_UNTIL (the round is still running), with no lives
        lost this pass and no crisis forecast. The panel covers the tower
        list for its few seconds; nothing is bought meanwhile."""
        ex = self.extras
        if ex is None or not getattr(ex, "wants_in_round", lambda: False)():
            return False
        if not self._in_round or dropped or rnd is None or self._in_crisis(rnd):
            return False
        first = getattr(self, "_first_round", None)
        if first is None:
            self._first_round = rnd             # the round was not read at Play: the first one read
            return False
        if rnd < first + 1:
            return False
        since = now - self._t_round_change
        return IN_ROUND_POWERS_AFTER <= since <= IN_ROUND_POWERS_UNTIL

    def _achievement_extras(self, phase="pre"):
        """Use Powers / place Instas for their achievements
        (powers.InGameExtras; the runner only passes one for a sure
        Easy/Medium game while a card wants it). phase "pre": before the
        first Play, nothing leaks meanwhile (Instas; Powers only when they
        do not wait for a round). phase "round": the Powers, once, in an
        early round (_in_round_powers_due). Any failure is logged and the
        game goes on as usual."""
        if self.extras is None:
            return
        if phase == "pre" and not getattr(self.extras, "wants_pre_round", lambda: True)():
            return
        try:
            if phase == "round":
                res = self.extras.run(self.g, self.menus, self.m, self._exclude(), phase="round")
                self.stats["achievement_powers_in_round"] = res
                return
            res = self.extras.run(self.g, self.menus, self.m, self._exclude())
            self.stats["achievement_extras"] = res
        except Exception:
            log.exception("achievement: powers/instas failed - carrying on")
            try:
                self.g.close_panels()
            except Exception:
                pass

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

    def _hold_for_clear(self, rnd, f, now):
        """Keep Play waiting, in a one-life game, while bloons of the round
        just sent are still on the track. True while waiting.

        The game lights the Play button again the moment a round's last
        bloon has been sent, not when the round is cleared, and the bot read
        that as "between rounds". Luminous Cove Impoppable (2026-11-06):
        round 98's MOABs were held at half the route when Play sent round
        99's 60 MOABs and 9 DDTs on top of them; the one life went 5 s later
        with $45,718 in the bank. Every round of that game had been sent
        early like this.

        The bloon watch (bloonwatch.py) decides: CLEAR_LOOKS looks in a row
        with no bloon on the route end the wait. A watch that is off or not
        ready never holds, and CLEAR_HOLD_MAX_S bounds the wait, so a
        misreading watch costs seconds, never the game's progress. Other
        modes keep the early send: with lives to spare it saves minutes."""
        rules = self.ex.rules
        if rnd is None or not rules.get("one_life") or rules.get("continuous"):
            return False
        if getattr(self, "_clear_off", False):
            return False
        watch = getattr(self, "watch", None)
        if watch is None or not watch.ready():
            return False
        holds = self._clear_hold
        state = holds.get(rnd)
        if state is False:
            return False
        if state is None:
            state = holds[rnd] = [now, 0]
        if now - state[0] > CLEAR_HOLD_MAX_S:
            log.info("round %d: bloons still seen after %.0f s - Play goes on", rnd, now - state[0])
            holds[rnd] = False
            self._clear_capped = getattr(self, "_clear_capped", 0) + 1
            if self._clear_capped >= CLEAR_CAPPED_ROUNDS:
                # Balance Impoppable (2026-11-06): the watch read bloons at
                # 30-33% of the route on a clear track every round, each wait
                # ran to the cap, and the game was quit as a timeout at
                # round 86 with the one life and $14,146 in hand
                log.warning("the bloon watch never clears on this map (%d rounds) - Play no longer "
                            "waits for it this game", self._clear_capped)
                self._clear_off = True
            return False
        try:
            depth = watch.look(f, now, list(self.g.towers.values()))
        except Exception:
            log.exception("bloon watch failed while holding Play - watch off")
            self.watch = None
            holds[rnd] = False
            return False
        if depth is None:          # a panel covers the field: this look does not count
            return True
        if depth > 0.0:
            if getattr(self, "_clear_noted", None) != rnd:      # said once a round
                self._clear_noted = rnd
                log.info("round %d: Play is lit but bloons are %.0f%% along the route - "
                         "waiting for the track to clear", rnd, 100 * depth)
            state[1] = 0
            return True
        state[1] += 1
        if state[1] < CLEAR_LOOKS:
            return True
        if getattr(self, "_clear_noted", None) == rnd:
            log.info("round %d: track clear after %.1f s - Play", rnd, now - state[0])
        holds[rnd] = False
        self._clear_capped = 0
        return False

    def _out_of_time(self, max_minutes):
        """True when the game should end as a timeout: past its time limit
        (`max_minutes`) with no new round for ROUND_STALL_S, or past
        GAME_HARD_LIMIT_FACTOR times the limit whatever happens.

        A game whose rounds keep coming is never quit for the clock alone:
        Balance Impoppable (2026-11-06) was quit at round 86 after 71
        minutes, alive and with $14,146, because the one-life wait for a
        clear track (_hold_for_clear) had added up to 25 s to each round. A
        CHIMPS game (95 rounds) at that pace needs about two hours."""
        now = time.time()
        elapsed = now - self.stats["start"]
        if elapsed < max_minutes * 60:
            return False
        if elapsed > GAME_HARD_LIMIT_FACTOR * max_minutes * 60:
            return True
        return now - getattr(self, "_t_round_change", self.stats["start"]) > ROUND_STALL_S

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

    def _follow_platforms(self, rnd):
        """Move the remembered spots of towers on moving platforms
        (Sanctuary) when the platforms have moved: they move when a round
        starts, which the executor tracks (Executor._pose_round, from the
        Play button and the screen). Cheap when nothing moved."""
        if self._carried is None or getattr(self._carried, "platforms", None) is None:
            return
        try:
            if rnd is not None:
                self.ex.now_round = rnd      # tick() would set it only after the move
            pose = self.ex._pose_round()
            self._carried.follow_platforms(pose, self.g.towers)
        except Exception:
            log.exception("moving towers with the platforms failed - carrying on")

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

    def _map_round(self, rnd):
        """The round the map's own round-driven changes (path phases, melting
        ground) have reached while the HUD shows `rnd`: one more in a
        continuous mode, where the next round's bloons are already coming.

        Erosion Apopalypse (2026-11-09, loss case 20261109_120839): the ice
        under n1, n2, a1 and the opener, which mapgeom.lost_ground melts at
        round 19, went while the HUD still read 18 (frames end_027: 17, all
        towers; end_028: 18, the bloons walking where they stood). The bot
        still counted them ("could not select n1"), rebuilt nothing, and
        146 lives were gone within seconds. In the other modes the same ice
        went at 18 -> 19 as modelled (Erosion Reverse, 2026-11-08 02:15)."""
        continuous = bool((getattr(self.ex, "rules", None) or {}).get("continuous"))
        return rnd + 1 if continuous and rnd is not None else rnd

    def _follow_track(self, rnd):
        """Paint only the paths bloons take in this round's phase and the
        next one (mapgeom.repaint_track), so towers go where bloons come now.
        Erosion Easy Primary Only was lost on round 11 with every tower
        beside paths bloons first take in rounds 37-91."""
        if self._phase_geom is None or rnd is None:
            return
        self._track_round = rnd
        rnd = self._map_round(rnd)
        try:
            from . import mapgeom
            if mapgeom.repaint_track(self.m, self._phase_geom, rnd, self._reverse):
                self.ex.track_changed()
            # Ground for new towers only has to last until this phase ends
            # (mapgeom.phase_end); towers on ground the map destroyed since
            # the last round seen are forgotten and their plan steps redone.
            # Both count in the map's trigger rounds: the HUD round plus the
            # lead learned in this game (_melt_check).
            ground_rnd = rnd + getattr(self, "_ground_lead", 0)
            horizon = mapgeom.phase_end(self._phase_geom, ground_rnd)
            if horizon != getattr(self.ex, "ground_horizon", None):
                self.ex.ground_horizon = horizon
                self.ex.track_changed()
            seen = getattr(self, "_ground_round", None)
            lost = mapgeom.lost_ground(self.m, self._phase_geom, seen, ground_rnd)
            if lost is not None and hasattr(self.ex, "ground_lost"):
                self.ex.ground_lost(lost)
            self._ground_round = ground_rnd
        except Exception:
            log.exception("repainting the track for round %s failed - carrying on", rnd)

    # how many rounds before its trigger round a melt is believed on evidence
    MELT_EARLY_MAX = 3

    def _melt_check(self, p):
        """Tower p could not be selected. When it stands on ground the map
        destroys within MELT_EARLY_MAX rounds, that melt has come early: it is
        applied now (every tower on that ground forgotten, plan steps redone)
        and the lead is kept for the rest of the game. True when p went so.

        Erosion Easy Primary Only (2026-11-10, Fast Track from round 10):
        the ice that triggers melt for round 19 and round 37 was gone in HUD
        rounds 17 and 35 (the game refunded the towers: cash $370 -> $5,322
        and $1,341 -> $16,063). Round 35 was spent clicking eleven missing
        towers for 35 s, one at a time, and round 36 had no defence: 107
        lives lost. Other Erosion games saw the melt on time or one round
        early (Apopalypse, see _map_round), so the lead is learned per game."""
        geom, rnd = self._phase_geom, getattr(self, "_track_round", None)
        if geom is None or rnd is None or getattr(self, "_ground_round", None) is None:
            return False
        try:
            from . import mapgeom
            now = self._ground_round
            soon = sorted({f for f in mapgeom.dynamics(geom).vanish.values()
                           if f is not None and now < f <= now + self.MELT_EARLY_MAX})
            for first in soon:
                lost = mapgeom.lost_ground(self.m, geom, now, first)
                if lost is None:
                    continue
                cx, cy = self.m.frac_to_cell(p.x, p.y)
                h, w = lost.shape
                if not (0 <= cy < h and 0 <= cx < w and lost[cy, cx]):
                    continue
                self._ground_lead += first - now
                log.warning("%s cannot be selected and stands on ground the map destroys for "
                            "round %d: the melt came %d round(s) early - applying it now",
                            p.tid, first, self._ground_lead)
                self._follow_track(rnd)
                return p.tid not in self.g.towers
        except Exception:
            log.exception("checking for an early melt failed - carrying on")
        return False

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
                load = self.ex.blimp_load(rnd)
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
        again).

        A firm hold (Executor.firm_hold: a game-ending blimp round ahead
        while the weak rating of this one is the damage model's alone)
        stays whole in a crisis round too: Bloonarius Prime Half Cash
        (2026-11-06) let reinforce spend round 40's MOAB money in four
        "crisis" rounds that all passed with no life lost."""
        saving = bool(getattr(self.ex, "saving_for_threat", False))
        if saving and getattr(self.ex, "firm_hold", False):
            return not dropped
        return saving and not dropped and not crisis

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

    def _plan_lets_reinforce(self, cash, rnd):
        """May reinforce spend this tick as far as the plan is concerned? A
        plan_first build's plan owns the bank (Executor.plan_first) except
        when both of these hold:

          * the bloons of the last round watched got PLAN_YIELD_DEPTH or
            more along the route (bloonwatch: the defence is really short,
            not only in the damage model) - or, in a mode with lives, the
            model rates the near round at its floor (YIELD_FLOOR, decided
            in plan_first_yields: X Factor Half Cash lost round 78 to camo
            ceramics that killed in one go, the bloons never past 81%);
          * the waiting plan step cannot be paid before a near round the
            damage model rates a crisis (Executor.plan_first_yields).

        The depth is what tells the real danger apart from the model's
        pessimism. Over the CHIMPS games of 2026-11-07..09, the won Cracked,
        Hedge, KartsNDarts and Lotus Island games had 22-60 rounds whose
        look-ahead was rated under 0.5, and none of them with the bloons past
        90% while the weak round was at most four rounds off; Moon Landing's
        round-59 loss (2026-11-09) had five in a row (rounds 55-59, 93-96%),
        its round-40 loss two. Skates' win had four (rounds 37-38, 97-98).
        No bloon watch counts as shallow bloons (only the floor rating of a
        mode with lives can let the cash go). Any other build: yes."""
        plan_first = getattr(self.ex, "plan_first", None)
        if plan_first is None or not plan_first():
            return True
        depths = getattr(self, "depths", None)
        deep = bool(depths) and (depths[-1].get("deepest") or 0.0) >= PLAN_YIELD_DEPTH
        yields = getattr(self.ex, "plan_first_yields", None)
        return bool(yields is not None and yields(cash, rnd, deep=deep))

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
        # plan steps given up for this game (journal), and those among them the
        # game refused spots for: the runner notes a lost game with any of
        # the latter as placement trouble on the map
        counts = self.ex.given_up_counts() if hasattr(self.ex, "given_up_counts") else None
        if counts is not None:
            # the build's own steps; threat answers and fills apart (one
            # threat tries a new tower of every kind: Sanctuary 2026-11-09
            # counted 130 of its 145 "plan steps given up" that way)
            self.stats["steps_given_up"] = counts["plan"]
            self.stats["answers_given_up"] = counts["other"]
        else:
            self.stats["steps_given_up"] = len(getattr(self.ex, "dead_steps", ()))
        self.stats["steps_refused"] = len(getattr(self.ex, "refused_dead_steps", ()))
        if self.depths:
            # the deepest point bloons reached in any round (bloonwatch.py)
            self.stats["bloon_depth"] = max(s["deepest"] for s in self.depths)
        self._count_last_lives(outcome)
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

    def _count_last_lives(self, outcome):
        """A defeat means the lives went to 0: the lives the tracker still
        trusted were lost too, even when it never confirmed the drop. Mesa
        ABR (2026-11-09, loss case 20261109_120238): round 27's 250 camo
        bloons took all 100 lives within ten seconds of the round's start,
        the Defeat card came before a falling read was confirmed, and the
        loss report said "lives lost: 0"."""
        if outcome != "defeat":
            return
        left = self._defeat_left = self._lives_left_at_defeat()
        if left > 0:
            self.stats["lives_lost"] = self.stats.get("lives_lost", 0) + left

    def _lives_left_at_defeat(self):
        """The lives a defeat took that the tracker never counted: at least
        what it still trusted, and at least the mode's starting lives less
        the leaks it did count - a defeat ends at 0, so the whole start went.

        The tracker alone undercounts fast defeats. It is fed only between
        purchases once the opening build is done, and its first read sets the
        count: Flooded Valley ABR (2026-11-09 21:12) lost 100 lives in five
        seconds right after the build, the tracker held 10 (one low read) and
        the report said 10 lost; Flooded Valley Apopalypse (21:20) leaked
        from 150 to 53 during the 40-second opening build (Apopalypse sends
        bloons from the start), the first read was 53 and the report said 53."""
        lives = getattr(self, "_lives", None)
        left = (lives.confirmed if lives is not None else None) or 0
        start = (getattr(self.ex, "rules", None) or {}).get("lives") or 0
        return max(left, start - self.stats.get("lives_lost", 0), 0)

    def _journal_end(self, outcome, rnd):
        """Write game_end; for a game not won, with its cause of death
        (journal.cause_of_death), returned for the log. A one-life game
        dies before the lives tracker can confirm the drop (a single read
        of 0, then the Defeat card), so a defeat without a leak in the
        journal for its round gets one, inferred, losing the last lives
        the tracker trusted."""
        try:
            if outcome == "defeat" and rnd not in self._leak_rounds:
                # the lives _count_last_lives found still uncounted (it runs
                # first); else what the tracker trusted, else the mode's start
                lives = getattr(self, "_defeat_left", None) or self._lives.confirmed
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
