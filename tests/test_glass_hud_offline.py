"""The glass HUD (tools/glass_scene.py, tools/glass_hud.py) and the HUD choice
in tools/overlay.py.

Offline: the widgets are drawn from fake log folders (the big HUD's test
fixtures) into images; the window side runs with fake windows. The one
real window made here is never shown. No lock, no control files.
Run: python tests/test_glass_hud_offline.py"""
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))

import hud_data as D                                    # noqa: E402
import glass_scene as G                                 # noqa: E402
from test_big_hud_offline import fake_root, live_hud    # noqa: E402

SCREENS = [(1920, 1200), (2560, 1600), (1680, 1050), (1440, 900)]     # 16:10, as BTD6 runs here
AREA_BUDGET = 0.15            # the widgets (and the buttons) cover well under this share of the screen


def overlaps(a, b):
    """Do two (x0, y0, x1, y1) rectangles share any area?"""
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def scaled(frac, w, h):
    return frac[0] * w, frac[1] * h, frac[2] * w, frac[3] * h


def area(r):
    return max(0, r[2] - r[0]) * max(0, r[3] - r[1])


def snapshot(in_game=True, hud=None, journal=True):
    now = time.time()
    with tempfile.TemporaryDirectory() as tmp:
        if hud is None:
            hud = live_hud(now) if in_game else {"phase": "menu", "t": now, "planner": live_hud(now)["planner"]}
        snap = D.Collector(fake_root(tmp, now, hud=hud, journal=journal), clock=lambda: now).poll()
    assert snap.in_game == in_game
    return snap, now


# -- where the widgets sit -----------------------------------------------------------------

def test_widgets_stay_inside_the_screen_and_off_the_games_ui():
    zones = G.game_ui_zones()
    for w, h in SCREENS:
        lay = G.Layout(w, h)
        screen = (0, 0, w, h)
        for in_game in (True, False):
            rects = dict(lay.rects(in_game), buttons=lay.buttons)
            for name, r in rects.items():
                assert 0 <= r[0] < r[2] <= w and 0 <= r[1] < r[3] <= h, (w, h, name, r)
                assert not overlaps(r, scaled(G.MIDDLE_OF_FIELD, w, h)), (w, h, name)
                if in_game:
                    for zone, frac in zones.items():
                        assert not overlaps(r, scaled(frac, w, h)), (w, h, name, zone, r)
            # nothing on top of anything else
            names = list(rects)
            for i, a in enumerate(names):
                for b in names[i + 1:]:
                    assert not overlaps(rects[a], rects[b]), (w, h, a, b)
            assert sum(area(r) for r in rects.values()) / (w * h) < AREA_BUDGET, (w, h, in_game)
            assert area(screen) > 0
        # the bottom cards stay below an open upgrade panel; the pill above the panel's name row
        box = scaled(G.upgrade_panel_box(), w, h)
        assert lay.rounds[1] >= box[3] and lay.decision[1] >= box[3]
        assert lay.pill[3] < h * G.LAYOUTS["16:10"]["upg_right"]["name"][1]


def test_pill_and_buttons_sit_between_cash_and_round():
    w, h = 1920, 1200
    lay = G.Layout(w, h)
    lives_cash = scaled(G.game_ui_zones()["lives and cash"], w, h)
    rnd = scaled(G.game_ui_zones()["round and settings"], w, h)
    assert lay.pill[0] >= lives_cash[2] and lay.buttons[2] <= rnd[0]
    assert lay.buttons[0] - lay.pill[2] == G.BUTTON_GAP and lay.buttons[3] > lay.pill[3]
    # the buttons' panel is as wide as hud_controls makes it
    import hud_controls
    assert lay.buttons[2] - lay.buttons[0] == hud_controls.BUTTON_PANEL_WIDTH == G.BUTTON_PANEL_WIDTH
    assert G.BUTTON_GAP == hud_controls.BUTTON_GAP
    # sizes scale with the screen's height
    big = G.Layout(2560, 1600)
    assert big.px(G.PILL_H) == round(G.PILL_H * 1600 / 1200 * G.UI_SCALE)


# -- what they draw --------------------------------------------------------------------------

def body_of(pic, lay):
    """The glass body inside a picture (its shadow margin taken off)."""
    m = lay.px(G.SHADOW)
    return pic.x + m, pic.y + m, pic.x + pic.image.width - m, pic.y + pic.image.height - m


def test_game_view_widgets():
    snap, now = snapshot(in_game=True)
    W, H = 1920, 1200
    scene = G.GlassScene(W, H)
    pics = scene.build_all(snap, now, (0, 0, W, H))
    assert set(pics) == {"field", "pill", "thoughts", "rounds", "decision", "ghosts"}
    for name in ("pill", "thoughts", "rounds", "decision"):
        assert body_of(pics[name], scene.lay) == tuple(getattr(scene.lay, name)), name
        img = pics[name].image
        assert img.mode == "RGBA"
        # see-through: the glass is neither invisible nor opaque in the body's middle row
        alphas = [img.getpixel((x, img.height // 2))[3] for x in range(img.width // 4, img.width // 2)]
        assert max(alphas) > 60 and min(alphas) < 200, (name, min(alphas), max(alphas))
        assert img.getpixel((0, 0))[3] < 40            # the corner: only a faint shadow
    # the village ghost (to place) sits at its planned spot; the ghosts' picture is only as big as they need
    vx, vy = D.project(0.377, 0.675, (0, 0, W, H))
    g = pics["ghosts"]
    assert g.x <= vx <= g.x + g.image.width and g.y <= vy <= g.y + g.image.height
    assert g.image.getpixel((int(vx - g.x), int(vy - g.y)))[3] > 0
    assert g.image.width * g.image.height < W * H / 4
    # BTD6 closed: no ghosts
    assert "ghosts" not in scene.build_all(snap, now, None)


def test_menu_view_widgets_and_the_pick_card_shrinks():
    snap, now = snapshot(in_game=False, journal=False)
    scene = G.GlassScene(1920, 1200)
    pics = scene.build_all(snap, now)
    assert set(pics) == {"pill", "thoughts", "pick", "progress"}
    (pick, phase, p, notes, runner_ups), h = scene.pick_content(snap)
    assert pick["map"] == "Hedge" and phase == "HF" and p == 0.8 and notes == ["learned track"]
    assert [c["map"] for c in runner_ups] == ["Logs"]
    assert h < scene.lay.px(G.PICK_H)                  # one runner-up, one note: shorter than the most
    pick_body, progress_body = body_of(pics["pick"], scene.lay), body_of(pics["progress"], scene.lay)
    assert pick_body[3] - pick_body[1] == h
    assert progress_body[1] == pick_body[3] + scene.lay.px(G.GAP)       # right under it
    # no planner yet: the card says so and stays small
    snap.planner, snap.next = None, None
    _content, h2 = scene.pick_content(snap)
    assert h2 < h and scene.pick(snap) is not None


def test_keys_change_only_with_what_a_widget_says():
    snap, now = snapshot(in_game=True)
    scene = G.GlassScene(1920, 1200)
    rect = (0, 0, 1920, 1200)
    first = {n: k for n, k, _b in scene.widgets(snap, now, rect)}
    later = {n: k for n, k, _b in scene.widgets(snap, now + 1.0 / G.PILL_FPS, rect)}
    assert [n for n in first if first[n] != later[n]] == ["pill"]      # only the heartbeat moves
    snap.margins_ahead = [(41, 0.6)]
    changed = {n: k for n, k, _b in scene.widgets(snap, now, rect)}
    assert [n for n in first if first[n] != changed[n]] == ["rounds"]
    scene.show_thoughts = False
    assert dict((n, k) for n, k, _b in scene.widgets(snap, now, rect))["thoughts"] == ("hidden",)


def test_text_helpers():
    f = G.font("regular", 14)
    assert G.fit("short", f, 500) == "short"
    cut = G.fit("a rather long line of text that cannot fit", f, 80)
    assert cut.endswith("…") and f.getlength(cut) <= 80
    lines = G.wrap("one two three four five six seven eight nine ten", f, 60, 2)
    assert len(lines) == 2 and lines[-1].endswith("…") and all(f.getlength(ln) <= 60 for ln in lines)
    assert G.mode_name("half_cash") == "half cash"


def test_widgets_draw_quickly():
    """Each widget draws in a few milliseconds once the glass is cached
    (generous bound: test machines vary)."""
    snap, now = snapshot(in_game=True)
    scene = G.GlassScene(1920, 1200)
    for name, _key, build in scene.widgets(snap, now, (0, 0, 1920, 1200)):
        build()                                      # fills the glass cache
        t0 = time.perf_counter()
        build()
        assert (time.perf_counter() - t0) * 1000 < 40, name


# -- the window side ---------------------------------------------------------------------------

class FakeWindow:
    def __init__(self, name):
        self.name, self.shown, self.hidden, self.on_top = name, 0, 0, 0
        self.picture = None

    def show(self, picture):
        self.shown += 1
        self.picture = picture

    def hide(self):
        self.hidden += 1

    def keep_on_top(self):
        self.on_top += 1

    def close(self):
        pass


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


def test_glass_hud_pushes_only_what_changed():
    import glass_hud
    import hud_controls
    now = time.time()
    old_rect = hud_controls.game_client_rect
    hud_controls.game_client_rect = lambda: (0, 0, 1920, 1200)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            collector = D.Collector(fake_root(tmp, now, hud=live_hud(now)), clock=lambda: now)
            clock = Clock(now)
            hud = glass_hud.GlassHud(None, collector=collector, clock=clock, size=(1920, 1200),
                                     make_window=FakeWindow)
            hud.frame()
            wins = hud.windows
            assert set(wins) == {"field", "pill", "thoughts", "rounds", "decision", "ghosts"}
            assert all(w.shown == 1 for w in wins.values())
            hud.frame()                                       # same instant: nothing drawn again
            assert all(w.shown == 1 for w in wins.values())
            clock.t += 1.0 / glass_hud.TICK_HZ * 2           # a heartbeat later: only the pill
            hud.frame()
            assert wins["pill"].shown == 2 and all(w.shown == 1 for n, w in wins.items() if n != "pill")
            hud.snap.in_game = False                          # menus: the game's cards go, the menu's come
            hud._t_poll = clock.t                             # (no new poll, which would read the game again)
            hud.frame()
            assert wins["rounds"].hidden == 1 and wins["decision"].hidden == 1 and wins["ghosts"].hidden == 1
            assert wins["field"].hidden == 1
            assert wins["pick"].shown == 1 and wins["progress"].shown == 1
    finally:
        hud_controls.game_client_rect = old_rect


def test_premultiplied_bgra():
    from PIL import Image
    import glass_hud
    img = Image.new("RGBA", (2, 1), (255, 0, 0, 128))
    assert glass_hud.premultiplied_bgra(img) == bytes([0, 0, 128, 128]) * 2


def test_layered_window_takes_a_picture_while_hidden():
    """UpdateLayeredWindow accepts our bitmap. The window is made off screen,
    never shown, and closed again."""
    if sys.platform != "win32":
        print("not Windows - skipped")
        return
    from PIL import Image
    import glass_hud
    win = glass_hud.LayeredWindow("test")
    try:
        win.push(Image.new("RGBA", (40, 20), (10, 20, 30, 120)), -5000, -5000)
        assert not win.visible
    finally:
        win.close()


def test_hud_choice():
    import overlay
    with tempfile.TemporaryDirectory() as tmp:
        old = overlay.STRIP_SWITCH, overlay.BIG_SWITCH
        overlay.STRIP_SWITCH, overlay.BIG_SWITCH = Path(tmp) / "HUD_STRIP", Path(tmp) / "HUD_BIG"
        env = os.environ.pop(overlay.HUD_ENV, None)
        try:
            assert overlay.hud_wanted() == "glass"
            os.environ[overlay.HUD_ENV] = "Big"
            assert overlay.hud_wanted() == "big"
            os.environ[overlay.HUD_ENV] = "strip"
            assert overlay.hud_wanted() == "strip"
            del os.environ[overlay.HUD_ENV]
            overlay.BIG_SWITCH.write_text("")
            assert overlay.hud_wanted() == "big"
            overlay.STRIP_SWITCH.write_text("")              # the strip wins over everything
            assert overlay.hud_wanted() == "strip"
            assert overlay.HUDS[0] == "glass" and overlay.HUDS[-1] == "strip"
        finally:
            overlay.STRIP_SWITCH, overlay.BIG_SWITCH = old
            if env is not None:
                os.environ[overlay.HUD_ENV] = env


def test_preview_composites_the_widgets():
    import hud_preview
    snap, now = snapshot(in_game=True)
    scene = G.GlassScene(800, 500)
    timed = hud_preview.time_glass(scene, snap, now, (0, 0, 800, 500), repeat=1)
    img = hud_preview.render_glass({n: t[0] for n, t in timed.items()}, (800, 500))
    assert img.size == (800, 500) and img.mode == "RGB"
    x0, y0, x1, y1 = scene.lay.decision
    assert img.getpixel(((x0 + x1) // 2, (y0 + y1) // 2)) != hud_preview.GREY[:3]     # the glass tints the grey


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all tests passed")
