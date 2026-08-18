"""The game's colour vocabulary.

One committed palette, carried over from the web prototype so both builds look
like the same game.  Nothing here imports pygame: these are plain tuples, which
keeps the palette usable from tests and from tools that never open a display.

Naming rule: colours are named for their *role*, not their hue, so a later art
pass can retune a value without every call site becoming a lie.
"""

from __future__ import annotations

from typing import Final

RGB = tuple[int, int, int]

# ── surfaces, darkest to lightest ────────────────────────────────────
VOID: Final[RGB] = (6, 5, 11)          # outside everything; the page backdrop
INK: Final[RGB] = (13, 11, 21)         # the playfield floor
PANEL: Final[RGB] = (21, 18, 31)       # HUD and dialog plates
PANEL_HI: Final[RGB] = (30, 26, 44)    # hovered plate
LINE: Final[RGB] = (36, 30, 54)        # hairline borders
LINE_HI: Final[RGB] = (58, 49, 84)     # emphasised border

# ── text ─────────────────────────────────────────────────────────────
BONE: Final[RGB] = (240, 229, 205)     # primary text
BONE_DIM: Final[RGB] = (184, 169, 139)  # secondary text
MUTED: Final[RGB] = (106, 99, 131)     # labels, captions
DISABLED: Final[RGB] = (70, 64, 88)

# ── the lantern: everything warm belongs to the player ───────────────
EMBER: Final[RGB] = (242, 169, 59)
EMBER_DARK: Final[RGB] = (168, 107, 31)
EMBER_CORE: Final[RGB] = (255, 196, 107)

# ── threat ───────────────────────────────────────────────────────────
BLOOD: Final[RGB] = (192, 58, 46)
BLOOD_DARK: Final[RGB] = (74, 24, 20)  # spent heart

# ── the three starting species, so silhouettes read apart at a glance ─
VILLAGER: Final[RGB] = (192, 58, 46)
BRUTE: Final[RGB] = (142, 42, 70)
CHILD: Final[RGB] = (220, 97, 82)
ASLEEP: Final[RGB] = (74, 67, 86)      # turned but not yet awake
DAYTIME_FOLK: Final[RGB] = (122, 111, 144)   # the same people, before dusk

# ── cold light: things that are not the lantern ──────────────────────
NIGHT_BLUE: Final[RGB] = (92, 110, 150)
MOON: Final[RGB] = (196, 222, 238)
SUGAR: Final[RGB] = (214, 138, 84)
SUGAR_BRIGHT: Final[RGB] = (234, 246, 251)

# ── arcane: spells, and only spells ──────────────────────────────────
ARCANE: Final[RGB] = (142, 107, 214)
ARCANE_BRIGHT: Final[RGB] = (180, 140, 255)

# ── semantic aliases ─────────────────────────────────────────────────
#: Used by the HUD and result screens so "good/bad" is one decision, made here.
GOOD: Final[RGB] = EMBER
BAD: Final[RGB] = BLOOD
BOSS: Final[RGB] = (214, 74, 122)


def with_alpha(colour: RGB, alpha: int) -> tuple[int, int, int, int]:
    """Return ``colour`` as an RGBA tuple.

    Exists because passing a 4-tuple to a pygame draw call on a surface with no
    alpha channel silently drops the alpha — writing it out at the call site
    makes that mistake visible instead of mysterious.
    """
    return (colour[0], colour[1], colour[2], max(0, min(255, alpha)))


def mix(a: RGB, b: RGB, t: float) -> RGB:
    """Blend two colours; ``t`` of 0 returns ``a`` and 1 returns ``b``."""
    t = max(0.0, min(1.0, t))
    return (
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
    )


def scale(colour: RGB, factor: float) -> RGB:
    """Brighten (>1) or darken (<1) a colour, clamped to the valid range."""
    return (
        max(0, min(255, int(colour[0] * factor))),
        max(0, min(255, int(colour[1] * factor))),
        max(0, min(255, int(colour[2] * factor))),
    )
