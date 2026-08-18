"""The pygame shell.

This is the only package allowed to touch a device — display, keyboard, mouse,
mixer, clock.  ``model`` must stay importable without any of them.
"""

from __future__ import annotations

from .game import Game, check, main

__all__ = ["Game", "check", "main"]
