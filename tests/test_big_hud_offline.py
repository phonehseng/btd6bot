"""The big HUD (tools/big_hud.py, hud_data.py, hud_scene.py) and the bot's side
of it (btd6bot/hudstate.py, Match._rate_ahead, forecast.margins).

Offline: fake log folders in a temporary directory; the Tk smoke test builds
the HUD on a withdrawn root (never shown, no window styles, no lock, no
control files) and skips itself where Tk cannot start."""
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from btd6bot import forecast as FC        # noqa: E402
from btd6bot import hudstate as HS        # noqa: E402
from btd6bot import match as M            # noqa: E402
from btd6bot.game import Game             # noqa: E402
import hud_data as D                      # noqa: E402
import hud_scene as S                     # noqa: E402

W, H = 1920, 1200


class Clock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


def stamp(t, level, source, msg):
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(t)) + f",123 {level} {source}: {msg}"


# -- the bot's side: hudstate ---------------------------------------------------------------

def test_hudstate_writes_whole_files_at_most_once_a_gap():
    with tempfile.TemporaryDirectory() as tmp:
        clock = Clock()
        hs = HS.HudState(Path(tmp) / "logs" / "hud.json", min_gap=1.0, clock=clock)
        hs.start_game(map="Logs", mode="hard", strategy="s", hero="obyn", end_round=80)
        doc = json.loads(hs.path.read_text(encoding="utf-8"))
        assert doc["phase"] == "game" and doc["game"]["map"] == "Logs" and doc["t"] == 1000.0
        clock.t += 0.5
        assert not hs.due()
        hs.update(cash=500)                  # not due: kept, not written
        assert "cash" not in json.loads(hs.path.read_text(encoding="utf-8"))
        hs.update(force=True, margins=[[5, 1.2]])
        doc = json.loads(hs.path.read_text(encoding="utf-8"))
        assert doc["cash"] == 500 and doc["margins"] == [[5, 1.2]]
        clock.t += 1.0
        assert hs.due()
        hs.end_game()
        assert json.loads(hs.path.read_text(encoding="utf-8"))["phase"] == "menu"
        hs.start_game(map="Quad")            # a new game forgets the old one's facts
        doc = json.loads(hs.path.read_text(encoding="utf-8"))
        assert "cash" not in doc and "margins" not in doc
        assert not list(Path(tmp, "logs").glob("*.tmp"))


def test_hudstate_off_until_enabled_and_never_raises():
    with tempfile.TemporaryDirectory() as tmp:
        off = HS.HudState(Path(tmp) / "hud.json", enabled=False)
        off.update(force=True, cash=1)
        assert not off.due() and not (Path(tmp) / "hud.json").exists()
        # the module's own writer is off until the bot enables it, so tests never touch the live file
        assert HS._default.enabled is False
        blocked = HS.HudState(Path(tmp))     # a folder where the file should be: the write fails quietly
        blocked.update(force=True, cash=1)


def test_plan_ahead_and_tower_sizes():
    plan = [{"do": "place", "id": "a", "kind": "dart", "at": [0.1, 0.2], "role": "dps"},
            {"do": "target", "id": "a", "to": "strong"},
            {"do": "upgrade", "id": "a", "to": "1-0-0"},
            {"do": "place", "id": "b", "kind": "ninja", "segment": [0, 1]}]
    ahead = HS.plan_ahead(plan, 0, n=2)
    assert ahead == [{"do": "place", "id": "a", "kind": "dart", "at": [0.1, 0.2]},
                     {"do": "upgrade", "id": "a", "to": "1-0-0"}]
    assert HS.plan_ahead(plan, 3) == [{"do": "place", "id": "b", "kind": "ninja"}]
    sizes = HS.tower_sizes(["dart", "no_such_tower"])
    foot, rng = sizes["dart"]
    from btd6bot import placement as P
    from btd6bot import towers as T
    assert abs(rng - T.TOWERS["dart"]["range"] * Game.PX_PER_UNIT) < 1e-3 and 0 < foot < rng
    # a kind the game data lacks gets the bot's own default footprint, no range - as the HUD assumes
    assert sizes["no_such_tower"] == [round(P.DEFAULT_RADIUS * Game.PX_PER_UNIT, 4), 0.0]
    assert abs(S.DEFAULT_FOOTPRINT - P.DEFAULT_RADIUS * Game.PX_PER_UNIT) < 1e-4


def test_forecast_margins_and_rate_ahead():
    assert FC.lowest({5: 1.4, 6: 0.7, 7: 2.0}) == (0.7, 6) and FC.lowest(None) is None and FC.lowest({}) is None
    f = FC.RoundForecast(None, "hard")             # no map: the forecast is off
    assert f.margins([], [5, 6]) is None and f.worst([], [5, 6]) is None

    class Each:
        def margins(self, towers, rounds):
            return {r: 3.0 - 0.5 * i for i, r in enumerate(rounds)}

    class WorstOnly:                               # an older fake: no per-round margins
        def worst(self, towers, rounds):
            return (0.9, rounds[-1])

    with tempfile.TemporaryDirectory() as tmp:
        old = HS._default
        HS._default = HS.HudState(Path(tmp) / "hud.json")
        try:
            m = SimpleNamespace(forecast=Each())
            assert M.Match._rate_ahead(m, [], [10, 11, 12]) == (2.0, 12)
            doc = json.loads((Path(tmp) / "hud.json").read_text(encoding="utf-8"))
            assert doc["margins"] == [[10, 3.0], [11, 2.5], [12, 2.0]]
            assert doc["weak"] == M.R.WEAK_MARGIN and doc["crisis"] == M.CRISIS_MARGIN
            assert M.Match._rate_ahead(SimpleNamespace(forecast=WorstOnly()), [], [10, 11]) == (0.9, 11)
        finally:
            HS._default = old


def test_match_and_runner_notes_for_the_hud():
    """Match._hud_update (each HUD tick, at most once a gap) and runner._show_choice (the planner's pick)."""
    from btd6bot import runner as RN
    from btd6bot.game import Placed
    with tempfile.TemporaryDirectory() as tmp:
        old = HS._default
        HS._default = HS.HudState(Path(tmp) / "hud.json", clock=Clock())
        try:
            ex = SimpleNamespace(plan=[{"do": "place", "id": "a", "kind": "dart", "at": [0.1, 0.2]},
                                       {"do": "place", "id": "b", "kind": "ninja", "at": [0.3, 0.4]},
                                       {"do": "upgrade", "id": "b", "to": "2-0-0"}],
                                 idx=1, waiting="plan step 1", save_goal=(600, 47))
            g = SimpleNamespace(towers={"a": Placed("a", "dart", 0.1, 0.2, [1, 0, 0])})
            m = SimpleNamespace(g=g, ex=ex, _lives=SimpleNamespace(confirmed=7), _hud_sizes={})
            M.Match._hud_update(m, 950, 12)
            doc = json.loads((Path(tmp) / "hud.json").read_text(encoding="utf-8"))
            assert (doc["round"], doc["cash"], doc["lives"], doc["save_goal"]) == (12, 950, 7, [600, 47])
            assert doc["towers"] == [["a", "dart", "1-0-0", 0.1, 0.2]] and [s["id"] for s in doc["plan"]] == ["b", "b"]
            assert set(doc["sizes"]) == {"dart", "ninja"} and set(m._hud_sizes) == {"dart", "ninja"}
            M.Match._hud_update(m, 1, 13)        # not due yet: nothing built, nothing written
            assert json.loads((Path(tmp) / "hud.json").read_text(encoding="utf-8"))["cash"] == 950

            def cand(name, p):
                return SimpleNamespace(map=name, mode="hard", s=SimpleNamespace(id="s"), p=p, score=10.0,
                                       minutes=9.0, tier="HF", notes=["learned track"])
            others = iter([cand(f"M{i}", 0.5) for i in range(10)])
            RN._show_choice(cand("Pick", 0.9), "HF", others)
            doc = json.loads((Path(tmp) / "hud.json").read_text(encoding="utf-8"))
            assert doc["planner"]["pick"]["map"] == "Pick" and doc["planner"]["pick"]["notes"] == ["learned track"]
            assert [c["map"] for c in doc["planner"]["runner_ups"]] == ["M0", "M1", "M2", "M3"]
            assert next(others).map == "M4"      # only the runner-ups shown were taken from the candidates
        finally:
            HS._default = old


# -- the HUD's side: parsing -------------------------------------------------------------------

def test_log_next_and_reinforce_lines():
    t = time.time()
    lines = [stamp(t, "I", "reinforce", "reinforce: saving for an old game"),
             stamp(t, "I", "runner", "NEXT: [LAST] Mushroom Grotto / reverse with solo_druid: score 14,566/min; "
                                     "p=0.48 (n=0), 8.5 min, mm 413 (estimate, first), last resort: under every bar"),
             "Traceback (most recent call last):",
             stamp(t, "W", "reinforce", "reinforce: upgrade d3 -> 0-0-5 ($21500) - round 59 goes 0.14 -> 1.65"),
             stamp(t, "I", "reinforce", "reinforce: saving for upgrade d2 -> 0-2-4 ($2050) - round 36 goes 0.75 -> 1.63")]
    recs = D.parse_log(lines)
    assert len(recs) == 4 and recs[0].source == "reinforce" and recs[2].level == "W"
    nxt = D.latest_next(recs)
    assert (nxt["phase"], nxt["map"], nxt["mode"], nxt["strategy"]) == ("LAST", "Mushroom Grotto", "reverse",
                                                                         "solo_druid")
    assert nxt["score"] == "score 14,566/min"
    assert nxt["notes"] == ["p=0.48 (n=0)", "8.5 min", "mm 413 (estimate, first)", "last resort: under every bar"]
    r = D.latest_reinforce(recs)
    assert r["saving"] and r["text"].startswith("saving for upgrade d2")
    assert D.latest_reinforce(recs[:2]) is None          # nothing said since the NEXT line: an old game's note
    assert D.parse_next("NEXT: [OWNER] Alpine Run / chimps with chimps_ninja_sun: the NEXT file")["notes"] == []


def journal_records(t0=1000.0):
    return [{"t": t0, "ev": "game_start", "rnd": 6, "map": "Alpine Run", "mode": "chimps",
             "strategy": "alpinerun_chimps", "hero": "obyn", "end_round": 100},
            {"t": t0 + 1, "ev": "place", "rnd": 6, "tid": "t1", "kind": "tack", "x": 0.281, "y": 0.589, "cost": 280,
             "why": {"source": "plan", "reason": "plan step 0", "step_idx": 0}},
            {"t": t0 + 2, "ev": "upgrade", "rnd": 7, "tid": "t1", "kind": "tack", "path": 2, "cross_before": "0-0-0",
             "cross_after": "0-1-0", "cost": 150, "why": {"source": "plan", "reason": "plan step 1"}},
            {"t": t0 + 3, "ev": "round", "rnd": 8, "cash": 700, "lives": 1, "margin": 1.3},
            {"t": t0 + 4, "ev": "place", "rnd": 8, "tid": "x9", "kind": "dart", "x": 0.5, "y": 0.5, "cost": 200,
             "why": {"source": "surplus", "reason": "spare cash: another dart"}},
            {"t": t0 + 5, "ev": "sell", "rnd": 9, "tid": "x9", "kind": "dart", "cross": "0-0-0", "spent": 200,
             "why": {"source": "useless", "reason": "barely reaches the track"}},
            {"t": t0 + 6, "ev": "hold", "rnd": 9, "why": "crisis", "margin": 0.44, "cash": 900},
            {"t": t0 + 7, "ev": "round", "rnd": 9, "cash": 950, "lives": 1, "margin": None}]


def test_read_journal():
    lines = [json.dumps(r) for r in journal_records()] + ['{"t": 1, "ev": "pla']     # a line half written
    view = D.read_journal(lines)
    assert view.game["map"] == "Alpine Run"
    assert view.towers == {"t1": ["tack", "0-1-0", 0.281, 0.589]}         # the sold dart is gone
    assert view.margins == [(8, 1.3)] and view.last_round["cash"] == 950 and view.outcome is None
    assert [d.source for d in view.decisions] == ["plan", "plan", "surplus", "useless", "hold"]
    assert view.decisions[1].what == "upgrade t1 0-0-0 -> 0-1-0  $150"
    assert view.decisions[-1].what == "hold round 9 (margin 0.44)" and view.decisions[-1].why == "crisis"
    ended = D.read_journal(lines + [json.dumps({"t": 2, "ev": "game_end", "rnd": 9, "outcome": "defeat",
                                                "round": 9})])
    assert ended.outcome == "defeat" and ended.end_round == 9


def test_journal_lines_keep_the_start_of_a_long_file():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "g.jsonl"
        recs = journal_records()
        filler = [json.dumps({"t": 1, "ev": "round", "rnd": 10 + i, "margin": 2.0, "pad": "x" * 200})
                  for i in range(3000)]
        p.write_text("\n".join([json.dumps(recs[0])] + filler) + "\n", encoding="utf-8")
        lines = D.journal_lines(p)
        assert json.loads(lines[0])["ev"] == "game_start" and len(lines) < 3000
        view = D.read_journal(lines)
        assert view.game["map"] == "Alpine Run" and view.margins[-1] == (3009, 2.0)


def test_wishes_ghosts_and_projection():
    towers = {"t1": ["tack", "0-1-0", 0.281, 0.589]}
    plan = [{"do": "upgrade", "id": "t1", "to": "0-2-0"},
            {"do": "place", "id": "e1", "kind": "engineer", "at": [0.377, 0.76]},
            {"do": "upgrade", "id": "e1", "to": "1-0-0"},
            {"do": "upgrade", "id": "t1", "to": "1-2-0"},
            {"do": "place", "id": "n4", "kind": "ninja", "near": ["t1"]},
            {"do": "upgrade", "id": "ghost_of_nothing", "to": "1-0-0"}]
    ghosts, unplaced = D.wishes(plan, towers)
    assert [(g.tid, g.placed, g.target, g.order) for g in ghosts] == [("t1", True, "1-2-0", 0),
                                                                       ("e1", False, "1-0-0", 1)]
    assert (ghosts[1].x, ghosts[1].y) == (0.377, 0.76) and [s["id"] for s in unplaced] == ["n4"]
    assert D.project(0.5, 0.25, (100, 50, 1600, 1000)) == (900, 300)
    wl = D.wish_list(plan, towers)
    assert [w.text() for w in wl[:3]] == ["upgrade t1 (tack) -> 0-2-0", "place e1 (engineer) -> 1-0-0 (2 steps)",
                                          "upgrade t1 (tack) -> 1-2-0"]
    # without hud.json: the strategy's plan less what the journal shows done
    steps = [{"do": "place", "id": "t1", "kind": "tack", "at": [0.281, 0.589]},
             {"do": "upgrade", "id": "t1", "to": "0-1-0"}, {"do": "upgrade", "id": "t1", "to": "0-2-0"},
             {"do": "place", "id": "e1", "kind": "engineer", "at": [0.377, 0.76]}]
    assert D.remaining_plan(steps, towers) == steps[2:]


def test_find_strategy():
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp, "strategies", "maps")
        d.mkdir(parents=True)
        (d / "alpinerun_chimps.yaml").write_text("id: alpinerun_chimps\nplan:\n  - {do: place, id: t1, kind: tack, "
                                                 "at: [0.281, 0.589]}\n", encoding="utf-8")
        (Path(tmp, "strategies") / "other.yaml").write_text("id: renamed\nplan:\n  - {do: place, kind: dart}\n",
                                                           encoding="utf-8")
        cache = {}
        assert D.find_strategy(tmp, "alpinerun_chimps", cache)[0]["at"] == [0.281, 0.589]
        assert D.find_strategy(tmp, "renamed", cache) == [{"do": "place", "kind": "dart"}]
        assert D.find_strategy(tmp, "missing", cache) == [] and D.find_strategy(tmp, None, cache) == []


def test_border_board():
    maps = {"A": "beginner", "B": "beginner", "C": "expert"}
    modes = ("easy", "hard", "chimps")
    medals = {"A": {"easy": True, "hard": True, "chimps": True}, "B": {"easy": True, "hard": False},
              "Z": {"easy": True}}
    board = D.border_board(medals, maps, ("beginner", "intermediate", "expert"), modes)
    assert [t.tier for t in board] == ["beginner", "intermediate", "expert"]
    a, b = board[0].maps
    assert (a.black, a.chimps, a.count, a.won) == (True, True, 3, (True, True, True))
    assert (b.black, b.chimps, b.count, b.won) == (False, False, 1, (True, False, False))
    assert board[0].black == 1 and board[1].maps == [] and board[2].maps[0].count == 0
    # the real map list: four tiers, Beginner first, 14 modes
    real_maps, tiers, keys = D.game_maps()
    assert tiers[0] == "beginner" and len(tiers) == 4 and len(keys) == 14 and "Monkey Meadow" in real_maps
    assert D.mode_difficulties()["chimps"]


# -- a fake bot folder ---------------------------------------------------------------------

def fake_root(tmp, now, hud=None, journal=True, account=True):
    root = Path(tmp)
    logs = root / "logs"
    (logs / "journal").mkdir(parents=True)
    (logs / "state.txt").write_text(time.strftime("%Y-%m-%d %H:%M:%S ") + "Alpine Run chimps - round 9\n",
                                    encoding="utf-8")
    (logs / "bot.log").write_text("\n".join([stamp(now, "I", "match", "round 9  cash 950  lives 1"),
                                             stamp(now, "I", "game", "upgraded t1 -> 0-1-0 for $150")]) + "\n",
                                  encoding="utf-8")
    (logs / "level.txt").write_text("Lv 147", encoding="utf-8")
    if journal:
        (logs / "journal" / "20261106_040000_AlpineRun_chimps.jsonl").write_text(
            "\n".join(json.dumps(r) for r in journal_records(now - 60)) + "\n", encoding="utf-8")
    if hud is not None:
        (logs / "hud.json").write_text(json.dumps(hud), encoding="utf-8")
    if account:
        (root / "data" / "accounts").mkdir(parents=True)
        (root / "data" / "current_account.txt").write_text("ABC123\n", encoding="utf-8")
        (root / "data" / "accounts" / "ABC123.json").write_text(json.dumps(
            {"medals": {"Monkey Meadow": {k: True for k in D.game_maps()[2]}, "Logs": {"easy": True}}}),
            encoding="utf-8")
    return root


def live_hud(now):
    return {"phase": "game", "t": now, "game": {"map": "Alpine Run", "mode": "chimps", "strategy": "alpinerun_chimps",
                                                "end_round": 100},
            "round": 41, "cash": 410, "lives": 1, "margins": [[41, 1.6], [42, 0.8], [43, 2.4]], "weak": 1.5,
            "crisis": 0.5, "towers": [["t1", "tack", "4-2-0", 0.281, 0.589]],
            "plan": [{"do": "upgrade", "id": "t1", "to": "5-2-0"},
                     {"do": "place", "id": "v1", "kind": "village", "at": [0.377, 0.675]}],
            "sizes": {"tack": [0.004, 0.064], "village": [0.005, 0.11]},
            "planner": {"phase": "HF", "pick": {"map": "Hedge", "mode": "chimps", "strategy": "s", "p": 0.8,
                                                "notes": ["learned track"]},
                        "runner_ups": [{"map": "Logs", "mode": "hard", "strategy": "s", "p": 0.6}]}}


def test_collector_in_a_game_with_hud_json():
    now = time.time()
    with tempfile.TemporaryDirectory() as tmp:
        root = fake_root(tmp, now, hud=live_hud(now))
        c = D.Collector(root, clock=lambda: now)
        snap = c.poll()
        assert snap.in_game and snap.round == 41 and snap.cash == 410 and snap.game["map"] == "Alpine Run"
        assert snap.margins_ahead == [(41, 1.6), (42, 0.8), (43, 2.4)] and snap.weak == 1.5
        assert snap.margins_past == [(8, 1.3)]
        assert [(g.tid, g.placed) for g in snap.ghosts] == [("t1", True), ("v1", False)]
        assert snap.state == "Alpine Run chimps - round 9" and snap.level == "Lv 147" and snap.flags == ()
        assert snap.board[0].maps[0].black and snap.board_modes[-1][0] == "chimps"
        again = c.poll()
        assert again.version == snap.version          # nothing changed: nothing re-read
        (root / "HOLD").write_text("x")
        assert c.poll().flags == ("HOLD",)


def test_collector_falls_back_and_degrades():
    now = time.time()
    with tempfile.TemporaryDirectory() as tmp:
        # an old hud.json: the journal (still being written) says a game is on;
        # the plan comes from the strategy file less what the journal shows done
        stale = dict(live_hud(now), t=now - 3600)
        root = fake_root(tmp, now, hud=stale)
        d = root / "strategies" / "maps"
        d.mkdir(parents=True)
        (d / "alpinerun_chimps.yaml").write_text(
            "id: alpinerun_chimps\nplan:\n  - {do: place, id: t1, kind: tack, at: [0.281, 0.589]}\n"
            "  - {do: upgrade, id: t1, to: 0-1-0}\n  - {do: place, id: e1, kind: engineer, at: [0.377, 0.76]}\n",
            encoding="utf-8")
        snap = D.Collector(root, clock=lambda: now).poll()
        assert snap.in_game and snap.round == 9 and snap.cash == 950 and snap.hud == {}
        assert [g.tid for g in snap.ghosts] == ["e1"] and snap.margins_ahead == []
        # the bot says the match is over
        (root / "logs" / "hud.json").write_text(json.dumps({"phase": "menu", "t": now}), encoding="utf-8")
        assert not D.Collector(root, clock=lambda: now).poll().in_game
    with tempfile.TemporaryDirectory() as tmp:     # nothing at all: an empty HUD, no error
        snap = D.Collector(Path(tmp), clock=time.time).poll()
        assert not snap.in_game and snap.log == [] and snap.board == [] and snap.quiet is None
        S.Scene(W, H).build_all(snap, time.time())


# -- the picture ---------------------------------------------------------------------------

KINDS = {"rectangle", "oval", "line", "arc", "text", "polygon"}


def test_scene_game_view():
    now = time.time()
    with tempfile.TemporaryDirectory() as tmp:
        snap = D.Collector(fake_root(tmp, now, hud=live_hud(now)), clock=lambda: now).poll()
    scene = S.Scene(W, H)
    game_rect = (0, 0, W, H)
    shapes = scene.build_all(snap, now, game_rect)
    assert {s.kind for s in shapes} <= KINDS
    texts = " ".join(s.opts["text"] for s in shapes if s.kind == "text")
    assert "THINKING" in texts and "41/100" in texts and "$410" in texts and "weakest ahead: round 42" in texts
    assert "upgrade t1 3-2-0" not in texts and "upgrade t1 0-0-0 -> 0-1-0  $150" in texts
    # the village ghost sits at its planned spot, its body the tower's footprint
    vx, vy = D.project(0.377, 0.675, game_rect)
    r = 0.005 * W
    assert any(s.kind == "oval" and s.opts.get("stipple") == "gray25" and s.coords == (vx - r, vy - r, vx + r, vy + r)
               for s in shapes)
    # the thought line runs from the panel's first wish to its ghost (the tack)
    tx, ty = D.project(0.281, 0.589, game_rect)
    assert any(s.kind == "line" and s.coords[2:] == (tx, ty) for s in scene.anim(snap, now + 1, game_rect))
    # the board is for the menus only
    assert not [s for s in shapes if s.kind == "text" and s.opts["text"] == "BLACK BORDERS"]
    # BTD6 closed: no ghosts, the panel stays
    assert not any(s.opts.get("stipple") for s in scene.build_all(snap, now, None))


def test_scene_menu_view_and_layer_keys():
    now = time.time()
    with tempfile.TemporaryDirectory() as tmp:
        hud = {"phase": "menu", "t": now, "planner": live_hud(now)["planner"]}
        snap = D.Collector(fake_root(tmp, now, hud=hud, journal=False), clock=lambda: now).poll()
    assert not snap.in_game
    scene = S.Scene(W, H)
    layers = scene.layers(snap, now)
    assert [name for name, _key, _build in layers] == list(S.LAYER_ORDER)
    shapes = [s for _n, _k, build in layers for s in build()]
    texts = [s.opts["text"] for s in shapes if s.kind == "text"]
    assert "BLACK BORDERS" in texts and "Hedge" in texts and "2. Logs / hard" in texts
    marks = scene._board_marks
    assert marks["Hedge"][1] == 1 and marks["Logs"][1] == 2 and len(marks) == 2   # the pick and its runner-up
    # the same snapshot a frame later: only the animation layer has a new key
    later = dict((n, k) for n, k, _b in scene.layers(snap, now + 0.1))
    assert all(later[n] == k for n, k, _b in layers if n != "anim")
    # the strip sits where the old HUD's did: 42% of the width, centred, 46 px tall at 1200
    assert S.Layout(W, H).strip == ((W - int(W * 0.42)) // 2, 0, (W - int(W * 0.42)) // 2 + int(W * 0.42), 46)


def test_strip_switch():
    import overlay
    with tempfile.TemporaryDirectory() as tmp:
        old, overlay.STRIP_SWITCH = overlay.STRIP_SWITCH, Path(tmp) / "HUD_STRIP"
        env = os.environ.pop(overlay.HUD_ENV, None)
        try:
            assert not overlay.strip_wanted()
            os.environ[overlay.HUD_ENV] = "Strip"
            assert overlay.strip_wanted()
            del os.environ[overlay.HUD_ENV]
            overlay.STRIP_SWITCH.write_text("")
            assert overlay.strip_wanted()
        finally:
            overlay.STRIP_SWITCH = old
            if env is not None:
                os.environ[overlay.HUD_ENV] = env


def test_tk_smoke_on_a_withdrawn_root():
    """The HUD builds and draws every layer on a real Tk canvas (the shapes'
    options are Tk's), on a root that is never shown."""
    import tkinter as tk
    import big_hud
    import hud_controls
    try:
        root = tk.Tk()
    except tk.TclError:
        print("no Tk here - skipped")
        return
    root.withdraw()
    now = time.time()
    old_rect = hud_controls.game_client_rect
    try:
        with tempfile.TemporaryDirectory() as tmp:
            collector = D.Collector(fake_root(tmp, now, hud=live_hud(now)), clock=lambda: now)
            hud_controls.game_client_rect = lambda: (0, 0, W, H)
            clock = Clock(now)
            hud = big_hud.BigHud(root, collector=collector, clock=clock)
            hud.frame()
            items = len(hud.canvas.find_all())
            assert items > 50 and hud.canvas.find_withtag("ghosts") and hud.canvas.find_withtag("panel")
            panel = hud.canvas.find_withtag("panel")
            clock.t += 1.0 / big_hud.FPS
            hud.frame()                        # a frame later: the panel is not rebuilt
            assert hud.canvas.find_withtag("panel") == panel
            assert hud.canvas.find_all()[-1] in hud.canvas.find_withtag("anim")   # animation on top
            hud.snap.in_game = False           # menus: the board is drawn, the ghosts go
            hud.layers.show(hud.scene.layers(hud.snap, clock.t, hud.game_rect))
            assert hud.canvas.find_withtag("board") and not hud.canvas.find_withtag("ghosts")
    finally:
        hud_controls.game_client_rect = old_rect
        root.destroy()


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all tests passed")
