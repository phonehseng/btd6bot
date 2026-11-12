"""The optimizer buys an answer to every threat strategy.coverage checks.

Up to 2026-11-11 tools/optimize_builds.py bought only what the damage model
asked for, so most of its builds held every round at margin 2 yet failed
strategy.coverage, which the runner checks before it plays anything: Dark
Dungeons and Quad Deflation (no BFB answer) were dropped, and their open
medals had no playable build. Optimizer._answer_threats now buys the
cheapest answer (strategy.ANSWERS) for each threat due in the window, and
run() measures the margins with it standing.

Run: python tests/test_optimizer_answers_offline.py"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import optimize_builds as O  # noqa: E402
from btd6bot import strategy as S  # noqa: E402

MAP, MODE = "Dark Dungeons", "deflation"


def _optimizer():
    """A Deflation optimizer for a fully unlocked account (no account file
    needed), Double Cash's $40,000 start."""
    return O.Optimizer(MAP, MODE, account=None, boosts={"double_cash": True})


def test_an_empty_plan_misses_the_threats():
    opt = _optimizer()
    missing = opt.missing_threats(O.Plan(MAP, MODE, None, "quincy"), 60)
    assert "bfb" in missing and "moab" in missing


def test_answers_are_bought_until_coverage_passes():
    opt = _optimizer()
    plan = O.Plan(MAP, MODE, None, "quincy")
    start = opt.econ.start_cash
    towers, cash, _n = opt._answer_threats(plan, [], start, 0, 31, list(range(31, 61)))
    assert opt.missing_threats(plan, 60) == []
    ok, missing = S.coverage(opt.as_strategy(plan), MODE, None)
    assert ok, missing
    # every purchase is paid for and recorded as a plan step with its reason
    assert abs((start - cash) - sum(s.action.cost for s in plan.steps)) < 1e-6
    assert all(s.why.startswith("answers ") for s in plan.steps)
    assert len(towers) == len({s.tid for s in plan.steps})


def test_threats_not_yet_due_are_left_for_later():
    """In an income mode only the threats of the coming rounds are bought:
    nothing for BFBs while the window ends at round 20."""
    opt = O.Optimizer(MAP, "medium", account=None)
    plan = O.Plan(MAP, "medium", None, "quincy")
    opt._answer_threats(plan, [], 5000, 0, 1, list(range(1, 21)))
    assert not any("bfb" in s.why for s in plan.steps)


def test_no_cash_buys_nothing():
    opt = _optimizer()
    plan = O.Plan(MAP, MODE, None, "quincy")
    towers, cash, _n = opt._answer_threats(plan, [], 0, 0, 31, list(range(31, 61)))
    assert towers == [] and cash == 0 and plan.steps == []


def test_surplus_cut_gives_back_the_last_xp_step_and_its_tower():
    note = O.SURPLUS_NOTE
    lines = ["plan:",
             "  - {do: place, id: a1, kind: ace, at: [0.1, 0.1]}   # R31: safety",
             f"  - {{do: place, id: ice9, kind: ice, at: [0.2, 0.2]}}   # R31: {note}",
             "  - {do: upgrade, id: ice9, to: 0-0-4}",
             "fill:"]
    cut = O._surplus_cut(lines)
    assert cut == ["plan:", lines[1], "fill:"]
    assert O._surplus_cut(cut) is None


def test_a_written_plan_gets_its_answers():
    """Quad Deflation (strategies/optimized/quad_deflation.yaml) lacked a
    BFB answer and spent its last dollars on XP surplus: --answer gives back
    surplus steps, buys an answer, and the plan then passes coverage with
    its margins re-checked."""
    import shutil
    import tempfile
    import yaml
    src = ROOT / "strategies" / "optimized" / "quad_deflation.yaml"
    tmp = Path(tempfile.mkdtemp()) / src.name
    shutil.copy(src, tmp)
    # the file as it was before its answers were added (ids "ans<n>")
    lines = [ln for ln in src.read_text(encoding="utf-8").splitlines() if "id: ans" not in ln]
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    before, after, worst0, worst = O.answer_plan(tmp, account=None)
    assert "bfb" in before
    plan = yaml.safe_load(tmp.read_text(encoding="utf-8"))
    ok, missing = S.coverage(plan, "deflation", None)
    assert ok, missing
    assert after == []
    assert worst >= min(worst0, O.SAFETY_MARGIN)
    assert abs(plan["optimizer"]["worst_margin"] - worst) < 0.006
    # ids stay unique, every upgrade names a tower the plan placed
    placed = [st["id"] for st in plan["plan"] if st["do"] == "place"]
    assert len(placed) == len(set(placed))
    assert all(st["id"] in placed for st in plan["plan"] if st["do"] == "upgrade")



def test_no_more_than_max_per_kind_towers_of_a_kind():
    """Dark Dungeons Deflation (2026-11-11): with no limit the greedy opened
    with 34 bare Skywardens and leaked from round 34. A kind with
    MAX_PER_KIND towers standing is offered upgrades only, by the search and
    by the threat answers."""
    opt = _optimizer()
    kind = "skywarden" if "skywarden" in opt.kinds else opt.kinds[0]
    towers = []
    for i in range(O.MAX_PER_KIND):
        towers.append(O.Tower(f"t{i}", kind, opt.setup.free_spot(kind, towers), (0, 0, 0), 0.0))
    places = [a for a in opt.actions(towers, 1e6) if a.tid is None]
    assert places and not any(a.kind == kind for a in places)
    assert any(a.kind == kind for a in opt.actions(towers, 1e6) if a.tid is not None)
    assert opt.room_for(kind, towers[:-1]) and not opt.room_for(kind, towers)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all tests passed")
