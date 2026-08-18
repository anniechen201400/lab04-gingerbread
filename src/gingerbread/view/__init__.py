"""Everything that turns state into pixels.

Read-only with respect to the rules: this layer observes a ``State`` and paints
it, and never decides an outcome.  If drawing could change a rule, the same run
would produce different results with the display switched off, and the headless
check would prove nothing.
"""

from __future__ import annotations

from .assets import AssetLibrary
from .board import Board
from .fonts import FontBook, load_font
from .lighting import Darkness
from .ui import UI, Scene, SceneStack, Stack, Theme

__all__ = [
    "AssetLibrary", "Board", "Darkness", "FontBook", "load_font",
    "UI", "Scene", "SceneStack", "Stack", "Theme",
]
