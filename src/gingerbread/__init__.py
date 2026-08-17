"""《糖果屋之後》 — After the Gingerbread House."""

from .model import (
    Meta, Phase, State,
    new_game, apply_action, is_terminal, snapshot, run_script,
)

__all__ = [
    "Meta", "Phase", "State",
    "new_game", "apply_action", "is_terminal", "snapshot", "run_script",
]
__version__ = "0.1.0"
