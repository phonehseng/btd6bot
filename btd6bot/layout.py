"""Screen layout as fractions of the game client area.

Calibrated on 1920x1200 (16:10) fullscreen, game v57.3. BTD6 anchors its HUD to
the screen edges, so other 16:10 resolutions work as-is; 16:9 needs the
alternate table below (selected automatically from the aspect ratio).
"""

LAYOUTS = {
    "16:10": {
        "playfield": (0.0, 0.04, 0.855, 0.96),
        "lives": (0.059, 0.045, 0.135, 0.11),   # right of the heart icon
        "cash": (0.183, 0.045, 0.32, 0.11),     # right of the coin icon
        # round counter moves left when an upgrade panel opens on the right
        "round": (0.705, 0.06, 0.815, 0.11),
        "round_shifted": (0.505, 0.06, 0.60, 0.11),
        "cancel_place": (0.829, 0.145),        # red X shown while a tower is held
        "tower_panel": (0.86, 0.17, 1.0, 0.84),
        "play_button": (0.963, 0.903),
        "gear": (0.828, 0.073),                 # in-game settings / pause
        # upgrade panel when the selected tower sits on the left half of the map
        "upg_right": {
            "box": (0.625, 0.03, 0.85, 0.90),
            "close": (0.84, 0.085),
            "paths": [(0.804, 0.47), (0.804, 0.61), (0.804, 0.75)],
            "cost_rows": [(0.76, 0.49, 0.85, 0.535), (0.76, 0.63, 0.85, 0.675), (0.76, 0.77, 0.85, 0.81)],
            "tier_rows": [(0.635, 0.40, 0.75, 0.50), (0.635, 0.54, 0.75, 0.64), (0.635, 0.68, 0.75, 0.78)],
            "target_prev": (0.658, 0.363),
            "target_next": (0.82, 0.363),
            "target_text": (0.66, 0.34, 0.82, 0.385),
            "sell": (0.799, 0.856),
            "name": (0.64, 0.065, 0.835, 0.11),
            "pops": (0.735, 0.103, 0.80, 0.14),   # pop counter under the name
        },
    },
}


def mirror(region):
    """Mirror an x-range / point horizontally inside the play field."""
    pf_right = LAYOUTS["16:10"]["playfield"][2]
    if len(region) == 2:
        x, y = region
        return (pf_right - x, y)
    x0, y0, x1, y1 = region
    return (pf_right - x1, y0, pf_right - x0, y1)


def shift(region, dx):
    if len(region) == 2:
        return (region[0] + dx, region[1])
    x0, y0, x1, y1 = region
    return (x0 + dx, y0, x1 + dx, y1)


def _with_left_panel(l):
    """The panel for towers on the right half opens at the far left of the
    screen with the same internal layout, and pushes the HUD to the right."""
    r = l["upg_right"]
    dx = -0.625
    l["upg_left"] = {k: ([shift(v, dx) for v in r[k]] if isinstance(r[k], list) else shift(r[k], dx))
                     for k in r}
    l["upg_left"]["hud_shift"] = 0.23
    l["upg_right"]["hud_shift"] = 0.0
    return l


for _l in LAYOUTS.values():
    _with_left_panel(_l)


def get(width, height):
    # Only 16:10 is calibrated; tools/calibrate.py writes overrides for others.
    return LAYOUTS["16:10"]
