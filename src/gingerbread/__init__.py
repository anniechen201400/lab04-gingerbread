"""《糖果屋之後》 — After the Gingerbread House.

Three layers, and the boundary between them is the point:

``model``   the rules.  Importable without pygame, deterministic, testable.
``view``    pixels.  Observes state, never decides an outcome.
``app``     devices.  The only place that touches display, keyboard or mixer.

The four contract functions are re-exported here so callers never have to know
which module inside ``model`` they live in.
"""

from .model import (ActionError, Meta, Mode, Phase, State, apply_action,
                    is_terminal, new_game, run_script, snapshot)

__all__ = [
    "Meta", "Mode", "Phase", "State", "ActionError",
    "new_game", "apply_action", "is_terminal", "snapshot", "run_script",
]
__version__ = "0.2.0"
