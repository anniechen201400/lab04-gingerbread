"""Pygame shell: the only module that touches devices.

One frame runs in exactly one direction::

    events + held keys -> InputAdapter -> action string
                       -> apply_action(state, action)      (model owns outcomes)
                       -> Renderer.draw(state)             (read-only)
                       -> display.flip() -> clock.tick()

The loop is written as ``async`` so the same file can be built for the web
with pygbag without changing any rule.
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass

import pygame

from . import model as m
from . import render as r
from .model import Meta, Phase, apply_action, is_terminal, new_game, snapshot

WINDOW_W = m.WIDTH
WINDOW_H = m.HEIGHT + r.HUD_HEIGHT + 62      # hud strip + action rail
FPS = 60

PROLOGUE: list[tuple[str, list[tuple[str, bool]]]] = [
    ("一｜森林", [
        ("那年冬天，家裡沒有東西可以吃了。", False),
        ("繼母說服爸爸，把我們帶進森林。", False),
        ("第一次，我偷偷撿了石頭，沿路留下記號。", False),
        ("所以我們回到了家。", False),
        ("第二次，我沒有石頭。", False),
        ("我只能把麵包撕成碎片，一路撒下。", False),
        ("可森林裡的鳥，把它們全吃光了。", False),
        ("這一次，我們真的迷路了。", True),
    ]),
    ("二｜糖果屋", [
        ("我們在森林深處找到一棟房子。", False),
        ("牆是麵包，窗戶是糖果。", False),
        ("老婆婆把我們帶進屋裡，給了我們吃不完的食物。", False),
        ("直到第二天——", False),
        ("我被關進了籠子。", False),
        ("葛蕾特被迫替她工作。", False),
        ("那時候我們才知道，這不是一棟房子。", False),
        ("是女巫的餐桌。", True),
    ]),
    ("三｜火焰", [
        ("女巫準備把我煮來吃。", False),
        ("她讓葛蕾特檢查爐火。", False),
        ("葛蕾特假裝不懂，騙她靠近爐子。", False),
        ("然後——", False),
        ("她把女巫推了進去。", False),
        ("她沒有哭。", True),
        ("我們燒了那間屋子。", False),
        ("從女巫的箱子裡拿走珍珠和寶石。", False),
        ("走了三天，我們回到了村子。", False),
    ]),
    ("四｜回家", [
        ("他們張開手臂迎接我們。", False),
        ("那時候，我以為他們是在為我們活著回來而高興。", False),
        ("後來我才知道。", False),
        ("他們看的不是我們。", False),
        ("是我們的口袋。", True),
        ("我們用珍珠換麵包，用寶石換食物。", False),
        ("那個冬天，村子第一次吃飽了。", False),
        ("直到最後一顆寶石也花完。", False),
    ]),
    ("五｜夜晚", [
        ("珍珠花完的那個冬天，村子開始餓。", False),
        ("田裡什麼都長不出來。連鳥都不來了。", False),
        ("白天，他們還是人。", False),
        ("會問好，會摸葛蕾特的頭，會問我們今天吃了沒有。", False),
        ("我學會在他們開口之前，先把東西分出去。", False),
        ("可太陽落下之後——", False),
        ("他們就不再是人了。", False),
        ("白天，我們要讓村子活下去。", True),
        ("晚上，我們得想辦法活下來。", True),
    ]),
]

GUIDE_STEPS = [
    "① 點下方的「分食給村民」",
    "② 再點畫面上任何一個村民",
    "③ 用剩下的行動點，選你自己要的準備",
]

TOOLS = [
    ("feed", "🍲", "分食給村民", "他今晚會猶豫：慢 40%、少一格血"),
    ("whet", "🔪", "磨利提燈", "攻擊 +1，永久保留到之後每一夜"),
    ("oil", "🛢", "添燈油", "光照 +26，永久保留到之後每一夜"),
    ("trap", "⚙", "設陷阱", "只有今晚有效，擋掉一隻"),
]


@dataclass
class Shell:
    """Presentation state.  Deliberately separate from the game rules."""

    screen: str = "prologue"       # prologue | play | nightwait | result
    chapter: int = 0
    revealed: bool = False
    reveal_at: int = 0
    tool: str | None = None
    guide: int = 0


class InputAdapter:
    """Turns pygame devices into one plain action string per frame."""

    EDGE_KEYS = {pygame.K_SPACE, pygame.K_RETURN, pygame.K_ESCAPE, pygame.K_r}

    def __init__(self) -> None:
        self.quit = False
        self.confirm = False
        self.restart = False
        self.clicked: tuple[int, int] | None = None

    def poll(self) -> None:
        """Drain the queue every frame; edge events are collected here."""
        self.confirm = False
        self.restart = False
        self.clicked = None
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.quit = True
            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_SPACE, pygame.K_RETURN):
                    self.confirm = True
                elif event.key == pygame.K_r:
                    self.restart = True
                elif event.key == pygame.K_ESCAPE:
                    self.quit = True
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self.clicked = event.pos

    def night_action(self) -> str:
        """Level-triggered controls become one move/swing/dash command."""
        keys = pygame.key.get_pressed()
        parts: list[str] = []
        if keys[pygame.K_a] or keys[pygame.K_LEFT]:
            parts.append("left")
        if keys[pygame.K_d] or keys[pygame.K_RIGHT]:
            parts.append("right")
        if keys[pygame.K_w] or keys[pygame.K_UP]:
            parts.append("up")
        if keys[pygame.K_s] or keys[pygame.K_DOWN]:
            parts.append("down")
        if keys[pygame.K_SPACE]:
            parts.append("swing")
        if keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]:
            parts.append("dash")
        if not parts:
            return "tick"
        if parts == ["swing"]:
            return "swing"
        return "move:" + "+".join(parts)


# ── headless smoke check (no display, no device) ─────────────────────
def smoke(seed: int = 42, frames: int = 360) -> dict[str, object]:
    """Run a fixed script with no window and return comparable evidence."""
    state = new_game(seed=seed)
    for i in range(4):
        state = apply_action(state, f"feed:{i}")
    state = apply_action(state, "begin_night")
    script = ["move:up+swing", "move:right+swing", "tick", "move:left+swing"]
    for i in range(frames):
        if is_terminal(state):
            break
        state = apply_action(state, script[i % len(script)])
    return snapshot(state)


class Game:
    def __init__(self, seed: int = 42) -> None:
        pygame.init()
        pygame.display.set_caption("糖果屋之後 · After the Gingerbread House")
        self.window = pygame.display.set_mode((WINDOW_W, WINDOW_H))
        self.board = pygame.Surface((m.WIDTH, m.HEIGHT))
        self.renderer = r.Renderer(self.board)
        self.clock = pygame.time.Clock()
        self.input = InputAdapter()
        self.shell = Shell()
        self.state = new_game(seed=seed)
        self.seed = seed
        self.font = self.renderer.font
        self.font_small = self.renderer.font_small
        self.font_big = self.renderer.font_big
        self.accumulator = 0.0

    # ── main loop ────────────────────────────────────────────────────
    async def run(self) -> None:
        running = True
        while running:
            dt_ms = self.clock.tick(FPS)
            self.input.poll()
            if self.input.quit:
                running = False

            if self.shell.screen == "prologue":
                self._update_prologue()
            elif self.shell.screen == "play":
                self._update_play(dt_ms)
            elif self.shell.screen == "nightwait":
                if self.input.confirm or self.input.clicked:
                    self.state = apply_action(self.state, "begin_night")
                    self.shell.screen = "play"
            elif self.shell.screen == "result":
                self._update_result()

            self._draw()
            pygame.display.flip()
            await asyncio.sleep(0)          # required for the web build
        pygame.quit()

    # ── screens ──────────────────────────────────────────────────────
    def _update_prologue(self) -> None:
        s = self.shell
        if s.reveal_at == 0:
            s.reveal_at = pygame.time.get_ticks()
        lines = PROLOGUE[s.chapter][1]
        done = pygame.time.get_ticks() - s.reveal_at > len(lines) * 340 + 500
        if self.input.confirm or self.input.clicked:
            if not (done or s.revealed):
                s.revealed = True
                return
            if s.chapter < len(PROLOGUE) - 1:
                s.chapter += 1
                s.revealed = False
                s.reveal_at = pygame.time.get_ticks()
            else:
                s.screen = "play"
        if self.input.restart:
            s.screen = "play"

    def _update_play(self, dt_ms: int) -> None:
        if self.state.phase is m.Phase.DAY:
            self._handle_day_click()
            self.accumulator += dt_ms / 1000.0
            while self.accumulator >= m.FIXED_DT:
                self.accumulator -= m.FIXED_DT
                self.state = apply_action(self.state, "tick")
            if self.state.action_points <= 0 or self.state.timer <= 0:
                self.shell.screen = "nightwait"
        elif self.state.phase is m.Phase.NIGHT:
            action = self.input.night_action()
            self.accumulator += dt_ms / 1000.0
            steps = 0
            while self.accumulator >= m.FIXED_DT and steps < 5:
                self.accumulator -= m.FIXED_DT
                self.state = apply_action(self.state, action)
                steps += 1
                if is_terminal(self.state):
                    break
            if is_terminal(self.state):
                self.shell.screen = "result"

    def _handle_day_click(self) -> None:
        pos = self.input.clicked
        if pos is None:
            return
        x, y = pos
        rail_top = r.HUD_HEIGHT + m.HEIGHT
        if y >= rail_top:
            index = min(3, max(0, x * 4 // m.WIDTH))
            key = TOOLS[index][0]
            if key in ("whet", "oil"):
                self.state = apply_action(self.state, key)
                self.shell.guide = max(self.shell.guide, 3)
            else:
                self.shell.tool = None if self.shell.tool == key else key
                if key == "feed" and self.shell.guide == 0:
                    self.shell.guide = 1
            return

        bx, by = x, y - r.HUD_HEIGHT
        if not (0 <= by < m.HEIGHT):
            return
        if self.shell.tool == "feed":
            for i, person in enumerate(self.state.villagers):
                if not person.fed and m.distance(bx, by, person.x, person.y) < 26:
                    self.state = apply_action(self.state, f"feed:{i}")
                    self.shell.tool = None
                    if self.shell.guide == 1:
                        self.shell.guide = 2
                    break
        elif self.shell.tool == "trap":
            self.state = apply_action(self.state, f"trap:{bx},{by}")
            self.shell.tool = None

    def _update_result(self) -> None:
        if self.input.clicked:
            x, y = self.input.clicked
            for i, key in enumerate(("atk", "light", "lives")):
                row = pygame.Rect(m.WIDTH / 2 - 190, 300 + i * 34, 380, 30)
                if row.collidepoint(x, y):
                    self.state = apply_action(self.state, f"buy:{key}")
                    return
        if self.input.confirm:
            move = "next_night" if self.state.phase is Phase.DAWN else "retry"
            self.state = apply_action(self.state, move)
            self.shell.screen = "play"
            self.shell.guide = 3
        elif self.input.restart:
            self.state = new_game(seed=self.seed)
            self.shell.screen = "play"

    # ── drawing ──────────────────────────────────────────────────────
    def _draw(self) -> None:
        self.window.fill(r.VOID)
        mouse = pygame.mouse.get_pos()
        board_mouse = (mouse[0], mouse[1] - r.HUD_HEIGHT)

        guide = None
        if self.state.meta.night == 1 and self.shell.guide < len(GUIDE_STEPS):
            guide = GUIDE_STEPS[self.shell.guide]
        self.renderer.draw(self.state, board_mouse, self.shell.tool, guide)
        self.window.blit(self.board, (0, r.HUD_HEIGHT))

        self._draw_hud()
        self._draw_rail()

        if self.shell.screen == "prologue":
            self._draw_prologue()
        elif self.shell.screen == "nightwait":
            self._draw_nightwait()
        elif self.shell.screen == "result":
            self._draw_result()

    def _draw_hud(self) -> None:
        pygame.draw.rect(self.window, r.PANEL, pygame.Rect(0, 0, WINDOW_W, r.HUD_HEIGHT))
        pygame.draw.line(self.window, r.LINE, (0, r.HUD_HEIGHT), (WINDOW_W, r.HUD_HEIGHT))
        st = self.state
        night = st.phase is m.Phase.NIGHT
        badge = "夜晚" if night else "白天"
        colour = r.NIGHT_BLUE if night else r.EMBER
        pygame.draw.rect(self.window, colour if not night else r.PANEL,
                         pygame.Rect(12, 14, 74, 26), 0 if not night else 1)
        text = self.font.render(badge, True, (20, 13, 2) if not night else r.NIGHT_BLUE)
        self.window.blit(text, text.get_rect(center=(49, 27)))

        x = 104
        for label, value in (("第幾夜", str(st.meta.night)),):
            self.window.blit(self.font_small.render(label, True, (106, 99, 131)), (x, 9))
            self.window.blit(self.font.render(value, True, r.BONE), (x, 26))
            x += 74

        # 愛心與行動點用畫的，不用字元——字型不一定有這些符號
        self.window.blit(self.font_small.render("葛蕾特", True, (106, 99, 131)), (x, 9))
        for i in range(st.meta.max_lives):
            colour = r.BLOOD if i < st.lives else (74, 24, 20)
            pygame.draw.circle(self.window, colour, (x + 6 + i * 15, 33), 5)
        x += max(84, st.meta.max_lives * 15 + 20)

        self.window.blit(self.font_small.render("行動點", True, (106, 99, 131)), (x, 9))
        for i in range(m.ACTION_POINTS):
            centre = (x + 6 + i * 15, 33)
            if i < st.action_points:
                pygame.draw.circle(self.window, r.EMBER, centre, 5)
            else:
                pygame.draw.circle(self.window, r.LINE, centre, 5, 1)
        x += 92

        for label, value in (("提燈", f"{st.meta.attack} 力 · {int(st.meta.light)} 光"),
                             ("糖霜", str(st.meta.sugar))):
            self.window.blit(self.font_small.render(label, True, (106, 99, 131)), (x, 9))
            self.window.blit(self.font.render(value, True, r.BONE), (x, 26))
            x += 130
        seconds = max(0, int(st.timer + 0.999))
        clock_text = self.font_big.render(f"{seconds // 60}:{seconds % 60:02d}", True,
                                          r.NIGHT_BLUE if night else r.EMBER)
        self.window.blit(clock_text, clock_text.get_rect(topright=(WINDOW_W - 14, 12)))
        frac = st.timer / st.timer_max if st.timer_max else 0
        pygame.draw.rect(self.window, r.LINE, pygame.Rect(0, r.HUD_HEIGHT - 3, WINDOW_W, 3))
        pygame.draw.rect(self.window, colour,
                         pygame.Rect(0, r.HUD_HEIGHT - 3, int(WINDOW_W * frac), 3))

    def _draw_rail(self) -> None:
        top = r.HUD_HEIGHT + m.HEIGHT
        pygame.draw.rect(self.window, r.INK, pygame.Rect(0, top, WINDOW_W, 62))
        pygame.draw.line(self.window, r.LINE, (0, top), (WINDOW_W, top))
        day = self.state.phase is m.Phase.DAY
        if not day:
            hint = "WASD／方向鍵移動　·　空白鍵揮燈　·　Shift 衝刺　·　走過去撿糖霜"
            text = self.font.render(hint, True, r.BONE_DIM)
            self.window.blit(text, text.get_rect(center=(WINDOW_W / 2, top + 31)))
            return
        width = WINDOW_W // 4
        for i, (key, glyph, name, why) in enumerate(TOOLS):
            box = pygame.Rect(i * width, top + 1, width - 1, 61)
            selected = self.shell.tool == key
            if selected:
                pygame.draw.rect(self.window, r.EMBER, box)
            colour = (20, 13, 2) if selected else (r.BONE if day else (70, 64, 88))
            sub = (64, 42, 6) if selected else (r.BONE_DIM if day else (52, 47, 66))
            self.window.blit(self.font.render(name, True, colour), (box.x + 14, box.y + 10))
            self.window.blit(self.font_small.render(why, True, sub), (box.x + 14, box.y + 34))
            pygame.draw.line(self.window, r.LINE, (box.right, top), (box.right, top + 62))

    def _veil(self, alpha: int = 242) -> None:
        layer = pygame.Surface((WINDOW_W, WINDOW_H), pygame.SRCALPHA)
        layer.fill((5, 4, 10, alpha))
        self.window.blit(layer, (0, 0))

    def _draw_prologue(self) -> None:
        self._veil()
        s = self.shell
        title, lines = PROLOGUE[s.chapter]
        head = self.font_big.render(title, True, r.EMBER)
        self.window.blit(head, head.get_rect(center=(WINDOW_W / 2, 96)))
        elapsed = pygame.time.get_ticks() - s.reveal_at
        y = 150
        for i, (line, strong) in enumerate(lines):
            if not s.revealed and elapsed < i * 340:
                break
            font = self.font_big if strong else self.font
            colour = r.EMBER if strong else (251, 244, 228)
            text = font.render(line, True, colour)
            self.window.blit(text, text.get_rect(center=(WINDOW_W / 2, y)))
            y += 34 if strong else 30
        tip = "空白鍵繼續" + ("　·　R 跳過序章" if s.chapter < len(PROLOGUE) - 1 else "　·　開始第一夜")
        text = self.font_small.render(tip, True, (106, 99, 131))
        self.window.blit(text, text.get_rect(center=(WINDOW_W / 2, WINDOW_H - 44)))
        for i in range(len(PROLOGUE)):
            colour = r.EMBER if i <= s.chapter else r.LINE
            pygame.draw.circle(self.window, colour,
                               (int(WINDOW_W / 2 - 28 + i * 14), WINDOW_H - 70), 3)

    def _draw_nightwait(self) -> None:
        self._veil(236)
        fed = self.state.fed_count
        total = len(self.state.villagers)
        head = self.font_big.render("天黑了", True, r.BONE)
        self.window.blit(head, head.get_rect(center=(WINDOW_W / 2, 190)))
        line = (f"你誰也沒有餵。{total} 個人今晚都會全力衝向葛蕾特。" if fed == 0
                else f"你餵了 {fed} 個人。他們今晚會猶豫，其餘 {total - fed} 個不會。")
        for i, text in enumerate([
            line,
            "WASD／方向鍵移動　·　空白鍵揮燈　·　Shift 衝刺",
            "紅色脈動箭頭＝有人正要從那裡進來，先去堵住。",
        ]):
            colour = r.BONE if i == 0 else (r.BONE_DIM if i == 1 else r.BLOOD)
            surf = self.font.render(text, True, colour)
            self.window.blit(surf, surf.get_rect(center=(WINDOW_W / 2, 240 + i * 30)))
        tip = self.font_small.render("空白鍵撐下去", True, r.EMBER)
        self.window.blit(tip, tip.get_rect(center=(WINDOW_W / 2, 360)))

    def _draw_result(self) -> None:
        self._veil(244)
        st = self.state
        won = st.phase is Phase.DAWN
        head = self.font_big.render(
            f"撐過了第 {st.meta.night} 夜" if won else "葛蕾特不見了", True, r.BONE)
        self.window.blit(head, head.get_rect(center=(WINDOW_W / 2, 60)))

        rows = [
            (f"分食 ×{st.fed_count}" if st.fed_count else "誰也沒餵",
             f"少了 {st.fed_count} 格血要打" if st.fed_count else "每一個人都用全力衝向她",
             st.fed_count == 0),
            (f"提燈 {st.meta.attack} 力", f"揮燈擊退 {st.stopped_by_lantern} 人", False),
            (f"陷阱 ×{len(st.traps)}" if st.traps else "沒設陷阱",
             f"夾住 {st.stopped_by_trap} 人" if st.traps else "沒有東西替你分擔",
             not st.traps),
            (f"光照 {int(st.meta.light)}",
             "看得夠遠，能提前迎上去" if st.meta.light > 100 else "光很小，他們走到面前你才看見",
             st.meta.light <= 100),
            ("撿到糖霜", f"{st.sugar_picked} 顆（累計 {st.meta.sugar}）", False),
            ("摸到葛蕾特", f"{st.reached_sister} 人", st.reached_sister > 0),
        ]
        y = 120
        for cause, effect, bad in rows:
            self.window.blit(self.font.render(cause, True, r.BLOOD if bad else r.BONE_DIM),
                             (m.WIDTH / 2 - 250, y))
            self.window.blit(self.font.render("→", True, r.EMBER_DARK), (m.WIDTH / 2 - 100, y))
            self.window.blit(self.font.render(effect, True, (217, 133, 124) if bad else r.BONE),
                             (m.WIDTH / 2 - 66, y))
            y += 26

        label = self.font_small.render("用糖霜換永久的東西（點一下購買）", True, r.EMBER_DARK)
        self.window.blit(label, (m.WIDTH / 2 - 190, 278))
        for i, key in enumerate(("atk", "light", "lives")):
            cost, name, desc = m.SHOP[key]
            row = pygame.Rect(m.WIDTH / 2 - 190, 300 + i * 34, 380, 30)
            affordable = st.meta.sugar >= cost
            pygame.draw.rect(self.window, r.PANEL, row)
            pygame.draw.rect(self.window, r.EMBER_DARK if affordable else r.LINE, row, 1)
            colour = r.BONE if affordable else (70, 64, 88)
            self.window.blit(self.font_small.render(f"{name} — {desc}", True, colour),
                             (row.x + 10, row.y + 7))
            self.window.blit(self.font_small.render(f"糖霜 {cost}", True,
                                                    r.SUGAR if affordable else (70, 64, 88)),
                             (row.right - 66, row.y + 7))

        tip = "空白鍵：" + ("進入下一夜" if won else "再撐一次這一夜") + "　·　R 從第一夜重來"
        text = self.font_small.render(tip, True, r.EMBER)
        self.window.blit(text, text.get_rect(center=(WINDOW_W / 2, WINDOW_H - 40)))


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="gingerbread")
    parser.add_argument("--check", action="store_true",
                        help="run one deterministic headless check and print JSON")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)

    if args.check:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        print(json.dumps(smoke(seed=args.seed), ensure_ascii=False, sort_keys=True))
        return 0

    asyncio.run(Game(seed=args.seed).run())
    return 0
