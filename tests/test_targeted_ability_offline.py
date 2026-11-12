"""The `do: ability` plan step: Adora's Blood Sacrifice on a tower the plan
names (Kali Maaaaaaaa, strategies/achievements/ach_kali_maaaaaaaa.yaml).

Three layers, each with fakes (no game, no screen):
- strategy.validate / readiness accept the step only in a form the bot can
  play (a known targeted ability of the strategy's own hero, a placed
  non-hero target, in the plan);
- Executor._try_ability waits for its round, the round being played and the
  hero's level, gives up on a target worth too little or a hero past the
  level cap, and tries the next candidate hotkey when a press armed nothing;
- Game.targeted_ability presses the key, clicks only the target's own spot
  and calls it done only when two clicks there open no panel; a box asking
  for money is cancelled, never confirmed;
- the AbilityPlanner presses no key at all once Blood Sacrifice may be
  unlocked: its assumed hotkey order could make any press arm it, and the
  bot's next click on a tower would then destroy that tower.
Run: python tests/test_targeted_ability_offline.py (also collectable by pytest)."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace as N

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import test_achievement_strats_offline as F   # noqa: E402  (the fakes)
from btd6bot import abilities as A            # noqa: E402
from btd6bot import game as G                 # noqa: E402
from btd6bot import strategy as S             # noqa: E402
from btd6bot import towers as T               # noqa: E402
from btd6bot.game import Placed               # noqa: E402

STEP = {"do": "ability", "name": "Blood Sacrifice", "target": "d1", "min_value": 72795,
        "when": {"round": 76, "hero_level_min": 7, "hero_level_max": 10}}
MAD = [0, 5, 0]       # $82,675 at Hard prices


def strat(step=None, hero="adora", where="plan"):
    plan = [{"do": "place", "id": "d1", "kind": "dartling"},
            {"do": "place", "id": "hero", "kind": "hero"}]
    s = {"id": "t", "hero": hero, "modes": ["hard"], "plan": plan}
    s.setdefault(where, []).append(dict(step or STEP))
    return s


# -- validation ---------------------------------------------------------------------

def test_the_step_validates_and_is_bot_ready():
    s = strat()
    assert S.validate(s) == [], S.validate(s)
    assert S.readiness(s) == [], S.readiness(s)     # `target: d1` is a tower, not a targeting mode


def test_bad_ability_steps_are_refused():
    def probs(**kw):
        step = dict(STEP)
        step.update({k: v for k, v in kw.items() if k not in ("hero", "where")})
        return " | ".join(S.validate(strat(step, kw.get("hero", "adora"), kw.get("where", "plan"))))
    assert "unknown targeted ability" in probs(name="Ball of Light")
    assert "the strategy's hero is quincy" in probs(hero="quincy")
    assert "is the hero" in probs(target="hero")
    assert "never placed" in probs(target="d9")
    assert "belongs in the plan" in probs(where="fill")
    assert "below Blood Sacrifice's unlock level 7" in probs(when={"round": 76, "hero_level_min": 5})
    assert "`when` takes only" in probs(when={"round": 76, "lives": 3})


def test_one_list_of_destructive_abilities():
    """The planner's never-press guard and the step's known abilities are the
    same set, and the step's hero and unlock level come from towers.HEROES."""
    assert set(S.TARGETED_ABILITIES) == A.DESTRUCTIVE_ABILITIES
    assert S.TARGETED_ABILITIES["Blood Sacrifice"] == {"hero": "adora", "level": 7}
    ab = next(a for a in T.HEROES["adora"]["abilities"] if a["name"] == "Blood Sacrifice")
    assert ab["use"] == "never"


# -- the executor ---------------------------------------------------------------------

class Game(F.FakeGame):
    """A fake game with Adora's panel level and a scripted ability outcome."""

    def __init__(self, level=7, outcomes=("done",)):
        super().__init__(hero="adora")
        self.level, self.outcomes, self.presses = level, list(outcomes), []
        self.towers["d1"] = Placed("d1", "dartling", 0.3, 0.4, tiers=list(MAD))
        self.towers["hero"] = Placed("hero", "hero", 0.5, 0.5)

    def hero_level(self, p):
        assert p.kind == "hero"
        return self.level

    def targeted_ability(self, key, p):
        self.presses.append((key, p.tid))
        r = self.outcomes.pop(0)
        if r == "done":
            self.towers.pop(p.tid)
            if self.level is not None:
                self.level += 10
        return r


def executor(game):
    ex = S.Executor(game, F.FakeModel(), strat(), "hard", F.full_account())
    ex.play_running = True
    return ex


def test_waits_for_its_round_then_sacrifices_the_target():
    g = Game()
    ex = executor(g)
    assert ex.try_step(STEP, 0, 75) == "wait" and g.presses == []
    assert ex.try_step(STEP, 0, 76) == "done"
    assert g.presses == [(1, "d1")] and "d1" not in g.towers


def test_waits_for_the_hero_level_and_the_round_being_played():
    g = Game(level=6)
    ex = executor(g)
    assert ex.try_step(STEP, 0, 77) == "wait" and g.presses == []
    assert g.fail_reason == "hero_level"
    g.level = 7
    ex.retry_at.clear()                  # (the level is looked at again after a pause)
    ex.play_running = False              # between rounds: the round's levels must count
    assert ex.try_step(STEP, 0, 77) == "wait" and g.presses == []
    ex.play_running = True
    assert ex.try_step(STEP, 0, 77) == "done"


def test_a_key_that_armed_nothing_makes_way_for_the_next_candidate():
    g = Game(outcomes=("not_armed", "done"))
    ex = executor(g)
    ex.abil = N(key_candidates=lambda name, rnd: [3, 2, 4], hero_round=70)
    assert ex.try_step(STEP, 0, 77) == "wait"
    assert ex.try_step(STEP, 0, 77) == "wait"          # the retry pause
    ex.retry_at.clear()
    assert ex.try_step(STEP, 0, 77) == "done"
    assert [k for k, _ in g.presses] == [3, 2]


def test_gives_up_when_it_can_never_go_right():
    g = Game(level=11)                                 # +10 would pass the cap of 20
    assert executor(g).try_step(STEP, 0, 78) == "skip" and g.presses == []
    g = Game()
    g.towers["d1"].tiers = [0, 4, 0]                    # $12,475: far from ten levels
    assert executor(g).try_step(STEP, 0, 78) == "skip" and g.presses == []
    g = Game(outcomes=("unclear",))                     # the screen did not show what happened
    assert executor(g).try_step(STEP, 0, 78) == "skip" and len(g.presses) == 1
    g = Game()
    del g.towers["d1"]
    assert executor(g).try_step(STEP, 0, 78) == "skip"
    g = Game(outcomes=["not_armed"] * S.Executor.ABILITY_MAX_TRIES)
    ex = executor(g)
    for _ in range(S.Executor.ABILITY_MAX_TRIES):
        ex.retry_at.clear()
        assert ex.try_step(STEP, 0, 78) == "wait"
    ex.retry_at.clear()
    assert ex.try_step(STEP, 0, 78) == "skip"


def test_waits_for_a_board_that_does_without_the_target():
    """min_margin: the step waits while the damage model rates any round
    left under it on the board without the target (Logs Hard, 2026-11-09:
    the M.A.D. was taken in round 76, rated 0.81 with it, and the ceramics
    it was shooting leaked at once)."""
    step = dict(STEP, when=dict(STEP["when"], min_margin=1.2))
    assert S.validate(strat(step)) == []
    bad = dict(STEP, when=dict(STEP["when"], min_margin=-1))
    assert "min_margin must be a positive number" in " | ".join(S.validate(strat(bad)))
    g = Game()
    ex = executor(g)
    rated = []

    def worst(towers, rounds):
        rated.append(([t.tid for t in towers], list(rounds)))
        return (2.0 if "n9" in [t.tid for t in towers] else 0.81, rounds[0])
    ex.forecast = N(worst=worst)
    assert ex.try_step(step, 0, 76) == "wait" and g.presses == [] and g.fail_reason == "margin"
    assert "d1" not in rated[-1][0] and "hero" in rated[-1][0]
    assert rated[-1][1] == list(range(76, 81))                 # every round left
    g.towers["n9"] = Placed("n9", "ninja", 0.6, 0.6, tiers=[4, 0, 2])   # the defence grew
    assert ex.try_step(step, 0, 76) == "done" and g.presses == [(1, "d1")]
    ex2 = executor(Game())
    ex2.forecast = N(worst=lambda towers, rounds: None)          # cannot rate: no sacrifice
    assert ex2.try_step(step, 0, 76) == "wait"


def test_a_waiting_ability_step_holds_no_cash():
    """Once only `do: ability` steps are left, plan_first lets go and the
    fill builds while the step waits (live, the waiting sacrifice step held
    every dollar from round 74 on and nothing else was bought)."""
    s = strat()
    s["plan_first"] = True
    s["fill"] = [{"do": "place", "kind": "ninja", "role": "support", "max": 2}]
    g = Game(level=6)                                            # the step waits for level 7
    ex = S.Executor(g, F.FakeModel(), s, "hard", F.full_account())
    ex.play_running = True
    assert ex.plan_first() and not ex._only_free_steps_left()    # placements still to go
    for _ in range(12):
        ex.tick(50000, 76)
    assert ex.plan[ex.idx]["do"] == "ability" and g.presses == []   # it waits
    assert not ex.plan_first() and ex._only_free_steps_left()
    assert g.placed.count("ninja") == 2, g.placed                 # the fill went on, to its max
    assert ex.waiting.startswith(f"plan step {ex.idx}") and not ex.plan_exhausted()


def test_without_a_panel_read_the_level_is_estimated_from_the_placement_round():
    g = Game(level=None)
    ex = executor(g)
    ex.hero_round = 70
    assert ex._hero_level_now(g.towers["hero"], 74) == (6, "estimate")
    assert ex.try_step(STEP, 0, 76) == "done"           # level 7 by round 76 (x1.08 Monkey Education)


# -- the ability planner ---------------------------------------------------------------

def test_blood_sacrifice_key_is_never_pressed_but_the_others_are():
    """Once Blood Sacrifice may be unlocked the planner holds its key only
    (AbilityPlanner.unsafe_keys); Long Arm of Light and the tower's Rocket
    Storm still fire, in emergencies and crisis rounds too."""
    pl = A.AbilityPlanner("adora", MODE_RULES_HARD)
    hero = N(tid="hero", kind="hero", tiers=[0, 0, 0])
    dart = N(tid="d1", kind="dartling", tiers=[0, 4, 0])      # Rocket Storm, on cooldown
    pl.update_towers([hero, dart], 70)
    pressed = set()
    for i in range(60):
        pressed |= set(pl.decide(1000.0 + i, 72, True))
    assert pressed                                   # Long Arm of Light / Rocket Storm early on
    assert pl.destructive_possible(72) is None
    rnd = next(r for r in range(70, 100) if pl.destructive_possible(r))
    pl.update_towers([hero, dart], rnd)
    unsafe = pl.unsafe_keys(rnd)
    assert unsafe
    pressed = set()
    for i in range(120):
        pressed |= set(pl.decide(2000.0 + i, rnd, True, lives_dropped=(i % 7 == 0), crisis=True))
    assert pressed and not pressed & unsafe, (pressed, unsafe)


def test_the_assumed_hotkey_order_matched_the_live_bar():
    """Logs Hard, 2026-11-09: Adora placed at round 70, d1 bought to 0-4-0
    (Rocket Storm) in round 71, Blood Sacrifice from round ~76. The bar
    showed Long Arm of Light, Rocket Storm/M.A.D., Blood Sacrifice (the
    recording, rec_20261109_150300.mkv), and key 3 armed Blood Sacrifice -
    the planner's acquisition order and its first candidate."""
    pl = A.AbilityPlanner("adora", MODE_RULES_HARD)
    hero = N(tid="hero", kind="hero", tiers=[0, 0, 0])
    pl.update_towers([hero], 70)
    pl.update_towers([hero, N(tid="d1", kind="dartling", tiers=[0, 4, 0])], 71)
    pl.update_towers([hero, N(tid="d1", kind="dartling", tiers=[0, 5, 0])], 76)
    order = [n for _, n, _, _, _ in pl.hotkeys(76)]
    assert order == ["hero:Long Arm of Light", "Rocket Storm", "hero:Blood Sacrifice"], order
    assert pl.key_candidates("Blood Sacrifice", 76)[0] == 3


def test_key_candidates_guess_first_and_skip_other_never_abilities():
    pl = A.AbilityPlanner("adora", MODE_RULES_HARD)
    hero = N(tid="hero", kind="hero", tiers=[0, 0, 0])
    pl.update_towers([hero, N(tid="d1", kind="dartling", tiers=[0, 4, 0])], 70)
    keys = dict((n, k) for k, n, _, _, _ in pl.hotkeys(85))
    cands = pl.key_candidates("Blood Sacrifice", 85)
    assert cands[0] == keys["hero:Blood Sacrifice"], (cands, keys)
    assert sorted(cands) == sorted(keys.values())
    # an unknown slot (level estimate behind): one past the last, then the rest
    early = pl.key_candidates("Blood Sacrifice", 71)
    assert early[0] == len(pl.hotkeys(71)) + 1
    # another 'never' ability's slot is never offered
    pl2 = A.AbilityPlanner("adora", MODE_RULES_HARD)
    pl2.update_towers([hero], 70)
    pl2._tower_seen["Overclock"] = (60, 0.0, 99)        # an engineer's, bought at round 60
    over = next(k for k, n, _, _, _ in pl2.hotkeys(85) if n == "Overclock")
    assert over not in pl2.key_candidates("Blood Sacrifice", 85)


MODE_RULES_HARD = S.MODE_RULES["hard"]


# -- the game ---------------------------------------------------------------------------

def _game(panels, boxes, screen_ok=True):
    """A Game whose panel reads (_open_side) and sacrifice-text reads
    (find_sacrifice_box, after each click that left the ability unarmed)
    are scripted; the armed signs read nothing (no frame, no words) unless
    a test scripts _armed_sign; key presses and clicks are recorded."""
    g = G.Game.__new__(G.Game)
    g.towers, g.why = {}, None
    g.events = []
    g.inp = N(press=lambda k: g.events.append(("press", k)),
              click=lambda x, y: g.events.append(("click", round(x, 3), round(y, 3))))
    g.screen_ok = lambda: screen_ok
    g.is_holding = lambda f=None: False
    g.fresh = lambda: None
    g._vision = lambda: N(read=lambda img=None, region=None: [])
    g._capture = lambda img, path: None
    g.closed = 0

    def close_panels():
        g.closed += 1
        return False
    g.close_panels = close_panels
    g._open_side = lambda f=None: panels.pop(0) if panels else None
    g._boxes = boxes
    return g


def _run(g):
    real_box, real_sleep = G.find_sacrifice_box, G.time.sleep
    G.find_sacrifice_box = lambda f, words: g._boxes.pop(0) if g._boxes else None
    G.time.sleep = lambda s: None
    try:
        p = Placed("d1", "dartling", 0.3, 0.4, tiers=list(MAD))
        g.towers["d1"] = p
        return g.targeted_ability(3, p), g
    finally:
        G.find_sacrifice_box, G.time.sleep = real_box, real_sleep


TOWER = ("click", 0.3, 0.4)


def test_two_clicks_without_a_panel_mean_the_tower_is_gone():
    r, g = _run(_game(panels=[None, None], boxes=[]))
    assert r == "done" and "d1" not in g.towers
    assert g.events == [("press", "3"), TOWER, TOWER]     # nothing clicked but the tower's spot


def test_its_own_panel_means_nothing_was_armed():
    r, g = _run(_game(panels=["upg_right"], boxes=[]))
    assert r == "not_armed" and "d1" in g.towers
    assert g.events == [("press", "3"), TOWER] and g.closed == 2   # before the press, and the panel


def test_a_sacrifice_box_is_confirmed_then_the_tower_must_be_gone():
    box = {"text": "Sacrifice?", "confirm": (0.55, 0.6), "cancel": (0.45, 0.6), "purchase": False}
    r, g = _run(_game(panels=[None, None, None], boxes=[dict(box), None, None]))   # read after each click
    assert r == "done"
    assert g.events == [("press", "3"), TOWER, ("click", 0.55, 0.6), TOWER, TOWER]


def test_a_box_that_asks_for_money_is_cancelled_never_confirmed():
    box = {"text": "Sacrifice for $500", "confirm": (0.55, 0.6), "cancel": (0.45, 0.6), "purchase": True}
    r, g = _run(_game(panels=[None], boxes=[dict(box)]))
    assert r == "unclear" and "d1" in g.towers
    assert ("click", 0.55, 0.6) not in g.events and g.events[-1] == ("click", 0.45, 0.6)


def test_a_banner_without_buttons_keeps_clicking_the_tower_only():
    banner = {"text": "Select a tower to sacrifice", "confirm": None, "cancel": None, "purchase": False}
    r, g = _run(_game(panels=[], boxes=[dict(banner)] * 5))
    assert r == "unclear"
    assert set(g.events[1:]) == {TOWER} and len(g.events) == 1 + G.Game.ABILITY_CLICKS


def test_still_armed_after_a_click_clicks_again():
    """The pentagram still over the tower after a click: the click did not
    take; the next click goes to the tower again and only two blank looks
    afterwards count it gone."""
    g = _game(panels=[None, None, None], boxes=[])
    signs = [("pentagram", None), ("pentagram", None), (None, []), (None, [])]
    g._armed_sign = lambda f, p: signs.pop(0)
    r, g = _run(g)
    assert r == "done" and g.events == [("press", "3"), TOWER, TOWER, TOWER]


FIXTURES = Path(__file__).resolve().parent / "fixtures"
D1 = (0.430, 0.308)        # where d1 stood on Logs Hard (logs/bot.log 2026-11-09 14:59:02)


def _fixture(name):
    import cv2
    img = cv2.imread(str(FIXTURES / name))
    assert img is not None, name
    return img


def test_the_armed_screen_is_recognised():
    """Live, Logs Hard 2026-11-09: key 3 armed Blood Sacrifice, but the
    check read "no sacrifice text" - the armed screen says "Select a
    Monkey". Now the banner (as OCR read it there) and the red pentagram
    over the target both tell it; the same spot unarmed (the hero-level
    frame of the same game, 5 s earlier) shows neither."""
    from btd6bot.vision import Word
    armed = _fixture("blood_sacrifice_armed.png")
    unarmed = _fixture("blood_sacrifice_unarmed.jpg")
    banner = [Word("Select a Monkey", 0.500, 0.077, 0.2, 0.03, 1.0), Word("76/80", 0.770, 0.086, 0.05, 0.03, 1.0)]
    assert G.pentagram_on(armed, *D1)
    assert not G.pentagram_on(unarmed, *D1)
    assert not G.pentagram_on(unarmed, 0.55, 0.44)          # the board's red tower, unarmed
    assert G.sacrifice_armed(armed, [], at=D1) == "pentagram"
    assert G.sacrifice_armed(unarmed, banner) == "banner"   # the words alone
    assert G.sacrifice_armed(unarmed, [], at=D1) is None
    elsewhere = [Word("Select a Monkey", 0.5, 0.6, 0.2, 0.03, 1.0)]   # not the banner's place
    assert G.sacrifice_armed(unarmed, elsewhere) is None


def test_the_armed_banner_is_read_off_the_fixture():
    """The OCR engine itself reads the banner off the captured frame (skipped
    where rapidocr is not installed)."""
    try:
        import rapidocr_onnxruntime  # noqa: F401
    except ImportError:
        return
    from btd6bot.vision import Vision
    armed = _fixture("blood_sacrifice_armed.png")
    words = Vision(None).read(region=G.ARMED_BANNER_REGION, img=armed)
    assert G.sacrifice_armed(armed, words) == "banner", words


def test_off_the_match_screen_nothing_is_pressed():
    r, g = _run(_game(panels=[], boxes=[], screen_ok=False))
    assert r == "refused" and g.events == []


def test_hero_level_from_the_panel_words():
    assert G.hero_level_from_text(["Adora", "Level 7", "Level 8", "$1,234"]) == 7
    assert G.hero_level_from_text(["LEVEL", "9"]) == 9
    assert G.hero_level_from_text(["Leve1 12"]) == 12
    assert G.hero_level_from_text(["Lvl17"]) == 17
    assert G.hero_level_from_text(["Adora", "1,234 pops"]) is None
    assert G.hero_level_from_text(["Level 45"]) is None


def test_find_sacrifice_box_marks_money_words():
    from btd6bot.vision import Word
    img = __import__("numpy").zeros((100, 160, 3), "uint8")
    words = [Word("Sacrifice tower?", 0.5, 0.4, 0.2, 0.03, 0.9)]
    box = G.find_sacrifice_box(img, words)
    assert box is not None and not box["purchase"] and box["confirm"] is None
    words.append(Word("$1,500", 0.5, 0.45, 0.1, 0.03, 0.9))
    assert G.find_sacrifice_box(img, words)["purchase"]
    assert G.find_sacrifice_box(img, [Word("Upgrade", 0.5, 0.4, 0.1, 0.03, 0.9)]) is None


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
    print("all tests passed")
