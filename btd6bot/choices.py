"""Glue between on-screen choices and the planner's preferences."""
import logging

from . import towers as T
from .vision import norm

log = logging.getLogger("choices")


def tower_chooser(account):
    """Callable for Menus.handle_tower_choice: (category_title, offered) -> display name."""
    from .planner import choose_tower_unlock

    def choose(category, offered):
        cat = category.lower() or None
        options = [T.find_tower(o) for o in offered if T.find_tower(o)]
        if cat not in ("primary", "military", "magic", "support"):
            cat = T.TOWERS[options[0]]["category"] if options else "primary"
        pick, reasons = choose_tower_unlock(cat, account)
        log.info("tower choice %s -> %s (%s)", cat, pick, "; ".join(reasons))
        return T.TOWERS[pick]["name"] if pick else None

    return choose


def same_tower(a, b):
    return norm(a) == norm(b)
