"""The darkness, and the lights cut into it.

The night is drawn as one dark sheet with holes punched through it.  Everything
here is measured rather than guessed; the notes below record what the numbers
said, because several of the obvious choices are wrong.

**Blend with ``BLEND_RGBA_MIN``, never ``BLEND_RGBA_SUB``.**  They cost the same
(0.027 ms per light) but subtract is additive-saturating: three dim overlapping
halos leave the sheet fully transparent where the model's ``max`` says it should
still be 45% dark.  The model decides whether a light-fearing monster freezes,
so a renderer that disagrees would freeze monsters in places the player sees as
black.  ``MIN`` keeps the two within 0.04 of each other across the whole field.

**Scale one master; never build a gradient per radius.**  A 512×512 master
built from 256 concentric circles costs 1.7 ms once.  Every other radius is a
``smoothscale`` of it — 0.41 ms at r=432, against 4.9 ms to build that size
directly, and the results differ by at most 4/255.

**Quantise the radius.**  The lantern flickers, so an unquantised cache key
churns: at a fully upgraded lantern it accumulated twenty textures and 114 MB in
ten seconds of play.  Rounding the key to an 8-pixel grid collapses that to five
buckets and also removes a one-pixel jitter at the light's edge.

**Do not render the darkness at low resolution.**  It is the obvious
optimisation and it measured *slower* at every scale tried, because upscaling a
225×130 sheet costs more than filling the full-size one.
"""

from __future__ import annotations

import math
from typing import Final

import pygame

from ..model import constants as C
from . import palette as P

#: Master resolution.  Large enough that scaling down to any in-game radius
#: stays smooth, small enough to bake in under two milliseconds.
_MASTER: Final = 512

#: Radii are rounded to this grid before being cached.
_QUANT: Final = 8

#: Hard ceiling on cached textures per kind.  Without it, anything that scales a
#: radius continuously — a boss aura, a fading spell — reproduces the very leak
#: this quantisation exists to fix.
_CACHE_LIMIT: Final = 24

#: How dark the night gets.  Not fully black: at pure black the ground texture
#: disappears entirely and the player loses all sense of the space.
#: Not fully opaque, and not pure black.  At 246 the unlit field was legible on
#: the machine it was tuned on and a black rectangle everywhere else — the
#: darkness has to hide detail, not remove the room.
_NIGHT_ALPHA: Final = 228
_NIGHT_COLOUR: Final = (6, 6, 14)


def _bake_mask() -> pygame.Surface:
    """Bake the master hole: opaque at the rim, transparent at the centre.

    Painted as 256 concentric circles.  The RGB stays white everywhere and only
    alpha varies — with ``BLEND_RGBA_MIN`` the colour channels are taken as a
    minimum too, so a darker RGB here would tint the night sheet toward black.
    """
    surface = pygame.Surface((_MASTER, _MASTER), pygame.SRCALPHA)
    surface.fill((255, 255, 255, 255))
    half = _MASTER // 2
    steps = 256
    for i in range(steps, 0, -1):
        t = i / steps                       # 1.0 at the rim, 0.0 at the wick
        # A tight clear core and a fast shoulder.  A wide, lazy falloff made the
        # lantern read as fog: everything within the radius was dimly visible
        # and nothing was ever properly hidden, which removes the tension the
        # darkness exists to create.  Clear to 35%, then climb hard.
        if t <= 0.40:
            alpha = 0
        else:
            shoulder = (t - 0.40) / 0.60
            alpha = int(255 * shoulder ** 0.95)
        pygame.draw.circle(surface, (255, 255, 255, max(0, min(255, alpha))),
                           (half, half), max(1, int(half * t)))
    return surface


def _bake_glow(colour: tuple[int, int, int], strength: float) -> pygame.Surface:
    """Bake an additive glow: opaque surface carrying premultiplied colour.

    ``BLEND_RGB_ADD`` ignores both the alpha channel and ``set_alpha``, so the
    brightness has to live in the RGB values themselves.  A glow built as an
    SRCALPHA surface with the intensity in its alpha blits as a solid square.
    """
    surface = pygame.Surface((_MASTER, _MASTER))
    surface.fill((0, 0, 0))
    half = _MASTER // 2
    steps = 96
    for i in range(steps, 0, -1):
        t = i / steps
        level = (1.0 - t) ** 2.2 * strength
        pygame.draw.circle(
            surface,
            (int(colour[0] * level), int(colour[1] * level), int(colour[2] * level)),
            (half, half), max(1, int(half * t)))
    return surface


class Darkness:
    """Draws the night.  Owns pixels and caches; decides nothing.

    Where a light *is* and how far it reaches are the model's business — the
    rules read the same geometry to decide whether a light-fearing monster
    freezes.  This class only turns that list into pixels.
    """

    def __init__(self, size: tuple[int, int]) -> None:
        self.size = size
        self._sheet = pygame.Surface(size, pygame.SRCALPHA)
        self._masters: dict[str, pygame.Surface] = {}
        self._cache: dict[tuple[str, int], pygame.Surface] = {}

    # ── lazy masters ─────────────────────────────────────────────────
    def warm_up(self) -> None:
        """Bake the masters up front.

        Baking lazily costs 8.8 ms on the first night frame — over half a frame
        natively and a visible stutter under WebAssembly.  Called from the
        loading path so the hitch happens where nothing is moving.  It cannot be
        done at import time: ``convert`` needs a display, and under pygbag the
        display is created inside the async main.
        """
        for name in ("mask", "warm", "cold"):
            self._master(name)

    def _master(self, name: str) -> pygame.Surface:
        found = self._masters.get(name)
        if found is not None:
            return found
        if name == "mask":
            built = _bake_mask().convert_alpha()
        elif name == "warm":
            built = _bake_glow(P.EMBER_CORE, 0.30).convert()
        else:
            built = _bake_glow(P.MOON, 0.16).convert()
        self._masters[name] = built
        return built

    def _texture(self, name: str, radius: float) -> pygame.Surface:
        """Return the named texture at a quantised radius, cached."""
        key = (name, max(_QUANT, int(radius) // _QUANT * _QUANT))
        found = self._cache.get(key)
        if found is not None:
            return found
        if len(self._cache) >= _CACHE_LIMIT:
            self._cache.clear()
        size = key[1] * 2
        scaled = pygame.transform.smoothscale(self._master(name), (size, size))
        built = scaled.convert_alpha() if name == "mask" else scaled.convert()
        self._cache[key] = built
        return built

    # ── the frame ────────────────────────────────────────────────────
    def draw(self, surface: pygame.Surface, lights, dusk: float,
             ticks: int) -> None:
        """Darken ``surface`` and cut ``lights`` out of it.

        ``lights`` comes straight from the model.  The flicker is applied *here
        only* — the radius the rules see must stay steady, or a monster at the
        light's edge would freeze and unfreeze sixty times a second and the
        snapshot would carry a value that means nothing.
        """
        if dusk <= 0:
            return

        alpha = int(_NIGHT_ALPHA * max(0.0, min(1.0, dusk)))
        self._sheet.fill((*_NIGHT_COLOUR, alpha))

        flicker = 1.0 + math.sin(ticks / 130.0) * 0.022

        placed: list[tuple[int, int, int, bool]] = []
        for light in lights:
            radius = light.radius * (1.0 if light.cold else flicker)
            texture = self._texture("mask", radius)
            half = texture.get_width() // 2
            left, top = int(light.x) - half, int(light.y) - half
            self._sheet.blit(texture, (left, top),
                             special_flags=pygame.BLEND_RGBA_MIN)
            placed.append((left, top, half, light.cold))

        surface.blit(self._sheet, (0, 0))

        # The warm cast, added on top.  Positioned from the same integers as the
        # mask: rounding them separately puts the glow a pixel off the hole and
        # leaves a coloured fringe down one side of every light.
        for left, top, half, cold in placed:
            glow = self._texture("cold" if cold else "warm", half)
            surface.blit(glow, (left, top), special_flags=pygame.BLEND_RGB_ADD)

    def memory_estimate(self) -> int:
        """Bytes held by cached textures — for the debug readout."""
        total = 0
        for surface in list(self._cache.values()) + list(self._masters.values()):
            total += surface.get_width() * surface.get_height() * 4
        return total
