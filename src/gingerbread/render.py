"""Read-only renderer.

This module observes a :class:`~gingerbread.model.State` and draws it.  It
never changes score, lives, entities or any other rule outcome — if drawing
code could change the model, the same run would produce different results with
the display switched off, and the headless smoke check would be worthless.
"""

from __future__ import annotations

import math
import os
from typing import Final

import pygame

from . import model as m

# ── palette (single dark-forest world, committed on purpose) ─────────
VOID: Final = (6, 5, 11)
INK: Final = (13, 11, 21)
PANEL: Final = (21, 18, 31)
LINE: Final = (36, 30, 54)
BONE: Final = (240, 229, 205)
BONE_DIM: Final = (184, 169, 139)
EMBER: Final = (242, 169, 59)
EMBER_DARK: Final = (168, 107, 31)
BLOOD: Final = (192, 58, 46)
SUGAR: Final = (214, 138, 84)
NIGHT_BLUE: Final = (92, 110, 150)
ASLEEP: Final = (74, 67, 86)

HUD_HEIGHT: Final = 54

_CJK_FONT_CANDIDATES: Final = (
    "assets/GameCJK-Subset.ttf",              # bundled subset; the web build has no system fonts
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "C:/Windows/Fonts/msjh.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
)


def load_font(size: int, root: str | None = None) -> pygame.font.Font:
    """Return a font that can draw Traditional Chinese, or the default."""
    base = root or os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    for candidate in _CJK_FONT_CANDIDATES:
        path = candidate if os.path.isabs(candidate) else os.path.join(base, candidate)
        if os.path.exists(path):
            try:
                return pygame.font.Font(path, size)
            except OSError:
                continue
    return pygame.font.Font(None, size)


def _light_texture(radius: int) -> pygame.Surface:
    """Pre-render one radial falloff used to cut holes in the darkness."""
    size = radius * 2
    surface = pygame.Surface((size, size), pygame.SRCALPHA)
    steps = 40
    for i in range(steps, 0, -1):
        t = i / steps                       # 1.0 at the rim, 0.0 at the wick
        if t <= 0.6:                        # bright core, matches the prototype
            strength = 1.0 - 0.12 * (t / 0.6)
        else:                               # soft shoulder out to nothing
            strength = 0.88 * (1.0 - (t - 0.6) / 0.4) ** 1.4
        pygame.draw.circle(surface, (0, 0, 0, int(255 * strength)),
                           (radius, radius), max(1, int(radius * t)))
    return surface


class Renderer:
    """Owns only pixels and cached surfaces — never a rule."""

    def __init__(self, surface: pygame.Surface, asset_root: str | None = None) -> None:
        self.surface = surface
        self.font_small = load_font(13, asset_root)
        self.font = load_font(16, asset_root)
        self.font_big = load_font(26, asset_root)
        self.font_mono = load_font(15, asset_root)
        self._light_cache: dict[int, pygame.Surface] = {}
        self._warm_cache: dict[int, pygame.Surface] = {}
        self._shadow = pygame.Surface((m.WIDTH, m.HEIGHT), pygame.SRCALPHA)
        self._ground = self._build_ground()

    # ── cached pieces ────────────────────────────────────────────────
    def _light(self, radius: int) -> pygame.Surface:
        key = max(8, int(radius))
        if key not in self._light_cache:
            self._light_cache[key] = _light_texture(key)
        return self._light_cache[key]

    def _warm(self, radius: int) -> pygame.Surface:
        key = max(8, int(radius))
        if key not in self._warm_cache:
            size = key * 2
            tint = pygame.Surface((size, size), pygame.SRCALPHA)
            steps = 20
            for i in range(steps, 0, -1):
                t = i / steps
                pygame.draw.circle(tint, (*EMBER, int(26 * (1 - t) ** 2)),
                                   (key, key), int(key * t))
            self._warm_cache[key] = tint
        return self._warm_cache[key]

    def _build_ground(self) -> pygame.Surface:
        """The clearing and treeline never change, so draw them once."""
        g = pygame.Surface((m.WIDTH, m.HEIGHT))
        g.fill(INK)
        cx, cy = int(m.SISTER_X), int(m.SISTER_Y)
        for r in range(340, 30, -6):
            t = 1 - (r - 30) / 310
            shade = (
                int(13 + 26 * t),
                int(11 + 21 * t),
                int(21 + 35 * t),
            )
            pygame.draw.circle(g, shade, (cx, cy), r)
        # engraved treeline around the edges
        for i in range(46):
            x = (i * 137.5) % m.WIDTH
            edge = x < 92 or x > m.WIDTH - 92
            y = (i * 61) % m.HEIGHT if edge else (-8 if i % 2 else m.HEIGHT + 8)
            h = 54 + (i % 5) * 24
            pygame.draw.polygon(
                g, VOID,
                [(x, y - h / 2), (x - 19, y + h / 2), (x + 19, y + h / 2)],
            )
        return g

    # ── public entry ─────────────────────────────────────────────────
    def draw(self, state: m.State, mouse: tuple[int, int] | None,
             tool: str | None, guide: str | None) -> None:
        night = state.phase is m.Phase.NIGHT
        self.surface.blit(self._ground, (0, 0))

        if state.phase is m.Phase.DAY:
            self._draw_approach_lines(state)
        self._draw_traps(state)
        if state.phase is m.Phase.DAY:
            self._draw_villagers(state)
        self._draw_drops(state)
        self._draw_sister(state)
        if night:
            self._draw_monsters(state)
        self._draw_player(state)
        if night:
            self._draw_darkness(state)
            self._draw_warnings(state)
            if state.surge_flash > 0:
                self._draw_surge(state)
        if state.phase is m.Phase.DAY:
            self._draw_day_overlay(state, mouse, tool, guide)

    # ── pieces ───────────────────────────────────────────────────────
    def _draw_approach_lines(self, state: m.State) -> None:
        """Telegraph: every villager's path to Gretel is visible while it is day."""
        for person in state.villagers:
            colour = (*SUGAR, 110) if person.fed else (*BLOOD, 88)
            self._dashed_line(
                (person.x, person.y), (m.SISTER_X, m.SISTER_Y), colour
            )

    def _dashed_line(self, a: tuple[float, float], b: tuple[float, float],
                     colour: tuple[int, int, int, int]) -> None:
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = math.hypot(dx, dy) or 1
        steps = int(length / 13)
        layer = pygame.Surface((m.WIDTH, m.HEIGHT), pygame.SRCALPHA)
        for i in range(steps):
            if i % 2:
                continue
            t0, t1 = i / steps, (i + 0.62) / steps
            pygame.draw.line(
                layer, colour,
                (a[0] + dx * t0, a[1] + dy * t0),
                (a[0] + dx * t1, a[1] + dy * t1), 1,
            )
        self.surface.blit(layer, (0, 0))

    def _silhouette(self, x: float, y: float, kind: str,
                    colour: tuple[int, int, int],
                    outline: tuple[int, int, int] | None = None) -> None:
        """Distinct body shapes so the three kinds read apart in one glance."""
        k = m.KINDS[kind]
        r = k.radius
        if kind == "brute":
            pygame.draw.ellipse(
                self.surface, colour,
                pygame.Rect(x - r * 1.15, y + 2 - r * 0.95, r * 2.3, r * 1.9))
            pygame.draw.circle(self.surface, colour, (int(x), int(y - r * 0.72)), int(r * 0.58))
        elif kind == "child":
            pygame.draw.circle(self.surface, colour, (int(x), int(y)), int(r * 0.82))
            pygame.draw.circle(self.surface, colour, (int(x), int(y - r * 0.78)), int(r * 0.6))
        else:
            pygame.draw.ellipse(
                self.surface, colour,
                pygame.Rect(x - r * 0.88, y + 1 - r, r * 1.76, r * 2))
            pygame.draw.circle(self.surface, colour, (int(x), int(y - r * 0.8)), int(r * 0.56))
        if outline:
            pygame.draw.circle(self.surface, outline, (int(x), int(y)), int(r + 6), 2)

    def _draw_villagers(self, state: m.State) -> None:
        for person in state.villagers:
            self._silhouette(
                person.x, person.y, person.kind,
                SUGAR if person.fed else (122, 111, 144),
                SUGAR if person.fed else None,
            )
            label = "猶豫" if person.fed else m.KINDS[person.kind].name
            text = self.font_small.render(label, True, SUGAR if person.fed else (122, 111, 144))
            self.surface.blit(
                text, text.get_rect(center=(person.x, person.y + m.KINDS[person.kind].radius + 16))
            )

    def _draw_monsters(self, state: m.State) -> None:
        for mo in state.monsters:
            k = m.KINDS[mo.kind]
            if mo.wake > 0:
                self._silhouette(mo.x, mo.y, mo.kind, ASLEEP)
                continue
            colour = EMBER if mo.hit_flash > 0 else (
                BLOOD if mo.kind == "villager" else
                (142, 42, 70) if mo.kind == "brute" else (220, 97, 82)
            )
            self._silhouette(mo.x, mo.y, mo.kind, colour,
                             SUGAR if mo.fed else None)
            pygame.draw.circle(self.surface, VOID,
                               (int(mo.x - k.radius * 0.3), int(mo.y - k.radius * 0.8)), 2)
            pygame.draw.circle(self.surface, VOID,
                               (int(mo.x + k.radius * 0.3), int(mo.y - k.radius * 0.8)), 2)
            if mo.hp < k.hp:
                w = k.radius * 2
                pygame.draw.rect(self.surface, VOID,
                                 pygame.Rect(mo.x - k.radius - 1, mo.y - k.radius - 11, w + 2, 4))
                pygame.draw.rect(self.surface, BONE,
                                 pygame.Rect(mo.x - k.radius, mo.y - k.radius - 10,
                                             w * (mo.hp / k.hp), 2))

    def _draw_traps(self, state: m.State) -> None:
        for trap in state.traps:
            colour = (70, 48, 73) if trap.used else (154, 148, 168)
            pygame.draw.circle(self.surface, colour, (int(trap.x), int(trap.y)), 11, 2)
            for i in range(6):
                a = i * math.pi / 3
                pygame.draw.line(
                    self.surface, colour,
                    (trap.x + math.cos(a) * 5, trap.y + math.sin(a) * 5),
                    (trap.x + math.cos(a) * 11, trap.y + math.sin(a) * 11), 2)

    def _draw_sister(self, state: m.State) -> None:
        bob = math.sin(pygame.time.get_ticks() / 620) * 1.3
        x, y = m.SISTER_X, m.SISTER_Y + bob
        glow = pygame.Surface((80, 80), pygame.SRCALPHA)
        pygame.draw.circle(glow, (*EMBER, 18), (40, 40), 34)
        self.surface.blit(glow, (x - 40, y - 40))
        pygame.draw.ellipse(self.surface, (232, 220, 194),
                            pygame.Rect(x - 9, y - 9, 18, 24))
        pygame.draw.circle(self.surface, (232, 220, 194), (int(x), int(y - 9)), 8)
        pygame.draw.arc(self.surface, (168, 113, 42),
                        pygame.Rect(x - 8, y - 19, 16, 16), 0, math.pi, 4)
        for i in range(state.meta.max_lives):
            hx = x - (state.meta.max_lives - 1) * 6 + i * 12
            hy = y - 30
            colour = BLOOD if i < state.lives else (74, 24, 20)
            pygame.draw.circle(self.surface, colour, (int(hx), int(hy)), 4)

    def _draw_drops(self, state: m.State) -> None:
        for drop in state.drops:
            pulse = math.sin(pygame.time.get_ticks() / 240 + drop.x) * 0.9
            halo = pygame.Surface((30, 30), pygame.SRCALPHA)
            pygame.draw.circle(halo, (*SUGAR, 60), (15, 15), int(10 + pulse))
            self.surface.blit(halo, (drop.x - 15, drop.y - 15))
            pygame.draw.circle(self.surface, (233, 164, 107),
                               (int(drop.x), int(drop.y)), int(4 + pulse * 0.4))

    def _draw_player(self, state: m.State) -> None:
        p = state.player
        shake = math.sin(pygame.time.get_ticks() / 26) * 2.4 if p.stun > 0 else 0

        if p.swing_anim > 0:
            k = p.swing_anim / m.SWING_ANIM
            facing = math.atan2(p.face_y, p.face_x)
            arc = pygame.Surface((m.WIDTH, m.HEIGHT), pygame.SRCALPHA)
            points = [(p.x, p.y)]
            for i in range(15):
                a = facing - m.SWING_ARC + (2 * m.SWING_ARC) * i / 14
                points.append((p.x + math.cos(a) * m.SWING_RANGE,
                               p.y + math.sin(a) * m.SWING_RANGE))
            pygame.draw.polygon(arc, (*EMBER, int(80 * k)), points)
            self.surface.blit(arc, (0, 0))

        flicker = 1 + math.sin(pygame.time.get_ticks() / 110) * 0.05
        halo = pygame.Surface((70, 70), pygame.SRCALPHA)
        pygame.draw.circle(halo, (*EMBER, 28), (35, 35), int(26 * flicker))
        self.surface.blit(halo, (p.x - 35, p.y - 35))

        body = (232, 144, 138) if p.stun > 0 else (
            (158, 150, 174) if p.invulnerable > 0
            and (pygame.time.get_ticks() // 90) % 2 else BONE)
        pygame.draw.ellipse(self.surface, body,
                            pygame.Rect(p.x + shake - 9.5, p.y - 10, 19, 25))
        pygame.draw.circle(self.surface, body, (int(p.x + shake), int(p.y - 9)), 8)

        lantern = EMBER if p.swing_cooldown <= 0 else (106, 74, 24)
        pygame.draw.circle(self.surface, lantern,
                           (int(p.x + p.face_x * 14), int(p.y + p.face_y * 14)),
                           int(5 * flicker))

        if state.phase is m.Phase.NIGHT and p.dash_cooldown > 0:
            frac = 1 - p.dash_cooldown / m.DASH_COOLDOWN
            rect = pygame.Rect(p.x - 21, p.y - 21, 42, 42)
            pygame.draw.arc(self.surface, (240, 229, 205, 90), rect,
                            -math.pi / 2, -math.pi / 2 + math.tau * frac, 2)

    def _draw_darkness(self, state: m.State) -> None:
        """Everything outside a prepared light is simply not there."""
        self._shadow.fill((2, 2, 6, 248))
        flicker = 1 + math.sin(pygame.time.get_ticks() / 130) * 0.022
        lights: list[tuple[float, float, float]] = [
            (state.player.x, state.player.y, state.meta.light * flicker),
            # Gretel keeps a small ember of her own: the person you are
            # protecting must never vanish, or the player loses the anchor
            # that makes the darkness meaningful instead of merely annoying.
            (m.SISTER_X, m.SISTER_Y, 58.0 * flicker),
        ]
        for trap in state.traps:
            if not trap.used:
                lights.append((trap.x, trap.y, m.TRAP_LIGHT))
        for x, y, r in lights:
            tex = self._light(int(r))
            self._shadow.blit(tex, (x - r, y - r), special_flags=pygame.BLEND_RGBA_SUB)
        self.surface.blit(self._shadow, (0, 0))

        # a soft candle cast, layered normally so it tints instead of blowing out
        for x, y, r in lights:
            tint = self._warm(int(r))
            self.surface.blit(tint, (x - r, y - r))

    def _draw_warnings(self, state: m.State) -> None:
        """Telegraphs pierce the darkness on purpose: readability over surprise."""
        pulse = 0.4 + math.sin(pygame.time.get_ticks() / 85) * 0.38
        for w in state.warnings:
            alpha = int(255 * pulse)
            layer = pygame.Surface((110, 110), pygame.SRCALPHA)
            pygame.draw.circle(layer, (*BLOOD, alpha), (55, 55), 21, 3)
            grow = 21 + (m.WARN_SECONDS - w.left) * 16
            pygame.draw.circle(layer, (*BLOOD, int(alpha * 0.35)), (55, 55), int(grow), 2)
            self.surface.blit(layer, (w.x - 55, w.y - 55))
            a = math.atan2(m.SISTER_Y - w.y, m.SISTER_X - w.x)
            tip = (w.x + math.cos(a) * 32, w.y + math.sin(a) * 32)
            left = (w.x + math.cos(a + 2.5) * 16, w.y + math.sin(a + 2.5) * 16)
            right = (w.x + math.cos(a - 2.5) * 16, w.y + math.sin(a - 2.5) * 16)
            pygame.draw.polygon(self.surface, BLOOD, [tip, left, right])

    def _draw_surge(self, state: m.State) -> None:
        k = state.surge_flash / 1.1
        layer = pygame.Surface((m.WIDTH, m.HEIGHT), pygame.SRCALPHA)
        pygame.draw.rect(layer, (*BLOOD, int(70 * k)),
                         pygame.Rect(0, 0, m.WIDTH, m.HEIGHT), 60)
        self.surface.blit(layer, (0, 0))
        text = self.font_big.render("他們一起來了", True, (*BONE,))
        text.set_alpha(int(255 * k))
        self.surface.blit(text, text.get_rect(center=(m.WIDTH / 2, 62)))

    def _draw_day_overlay(self, state: m.State, mouse: tuple[int, int] | None,
                          tool: str | None, guide: str | None) -> None:
        message = guide or "這些人今晚都會來 — 你現在對誰好，晚上就少一個麻煩"
        colour = EMBER if guide else BONE_DIM
        text = self.font.render(message, True, colour)
        rect = text.get_rect(center=(m.WIDTH / 2, 30))
        box = rect.inflate(28, 14)
        panel = pygame.Surface(box.size, pygame.SRCALPHA)
        panel.fill((6, 5, 11, 190))
        self.surface.blit(panel, box.topleft)
        pygame.draw.rect(self.surface, EMBER_DARK if guide else LINE, box, 1)
        self.surface.blit(text, rect)

        if tool == "trap" and mouse:
            pygame.draw.circle(self.surface, EMBER_DARK, mouse, 22, 1)
