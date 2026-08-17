"""Pure domain model for 《糖果屋之後》 (After the Gingerbread House).

This module must stay importable **without pygame**.  It contains no display,
no keyboard, no clock and no wall-clock reads.  Every rule is a deterministic
function of (state, action) with a fixed time step, so any run can be replayed
and any failure can be reproduced.

Design contract carried from the course:
    same state + same action + same dt  ->  same next state

The renderer only observes state; it never decides an outcome.
"""

from __future__ import annotations

import math
import random
from copy import deepcopy
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Final

# ── world constants ──────────────────────────────────────────────────
WIDTH: Final = 900
HEIGHT: Final = 520
SISTER_X: Final = WIDTH / 2
SISTER_Y: Final = HEIGHT / 2

FIXED_DT: Final = 1.0 / 60.0   # one tick; fixed on purpose so replays match
DAY_SECONDS: Final = 35.0
NIGHT_SECONDS: Final = 50.0
ACTION_POINTS: Final = 4

# ── player constants ─────────────────────────────────────────────────
PLAYER_RADIUS: Final = 13.0
WALK_SPEED: Final = 196.0
DASH_SPEED: Final = 560.0
DASH_TIME: Final = 0.16
DASH_COOLDOWN: Final = 1.4
SWING_RANGE: Final = 74.0
SWING_ARC: Final = 0.78          # radians either side of facing
SWING_COOLDOWN: Final = 0.55
SWING_ANIM: Final = 0.16
SWING_SLOWDOWN: Final = 0.42     # movement multiplier while the lantern swings
STUN_TIME: Final = 0.30
INVULNERABLE_TIME: Final = 1.20
KNOCKBACK_SPEED: Final = 260.0

# ── starting meta values ─────────────────────────────────────────────
START_ATTACK: Final = 1
START_LIGHT: Final = 66.0
START_LIVES: Final = 3
LIGHT_PER_OIL: Final = 26.0

# ── night pressure ───────────────────────────────────────────────────
SISTER_REACH: Final = 26.0
WARN_SECONDS: Final = 1.05
TRAP_RADIUS: Final = 18.0
TRAP_LIGHT: Final = 30.0


class Phase(str, Enum):
    """Top-level lifecycle.  ``str`` mixin keeps snapshots JSON-safe."""

    PROLOGUE = "prologue"
    DAY = "day"
    NIGHT = "night"
    DAWN = "dawn"          # survived the night
    LOST = "lost"          # Gretel was taken


@dataclass(frozen=True, slots=True)
class Kind:
    """Immutable species record.  A tuple-like fixed record, never mutated."""

    name: str
    hp: int
    speed: float
    radius: float
    sugar: int
    knockable: bool


KINDS: Final[dict[str, Kind]] = {
    "villager": Kind("村民", hp=2, speed=38.0, radius=10.0, sugar=1, knockable=True),
    "brute": Kind("壯漢", hp=4, speed=29.0, radius=15.0, sugar=2, knockable=False),
    "child": Kind("孩子", hp=1, speed=73.0, radius=8.0, sugar=1, knockable=True),
}

SHOP: Final = {
    "atk": (5, "磨利提燈", "攻擊 +1，永久"),
    "light": (4, "加大燈罩", "光照 +26，永久"),
    "lives": (7, "葛蕾特的勇氣", "她多一格血，永久"),
}


@dataclass(slots=True)
class Villager:
    """A townsfolk during the day; the same person turns at night."""

    kind: str
    x: float
    y: float
    fed: bool = False
    wake: float = 0.0          # seconds before this one turns


@dataclass(slots=True)
class Monster:
    """A turned villager walking toward Gretel."""

    kind: str
    x: float
    y: float
    hp: int
    speed: float
    fed: bool
    wake: float = 0.0
    hit_flash: float = 0.0
    knockback: float = 0.0


@dataclass(slots=True)
class Warning:
    """A telegraphed arrival.  Visible through the darkness on purpose."""

    x: float
    y: float
    kind: str
    left: float


@dataclass(slots=True)
class Drop:
    x: float
    y: float
    value: int


@dataclass(slots=True)
class Trap:
    x: float
    y: float
    used: bool = False


@dataclass(slots=True)
class Player:
    """Hansel.  Owns his own position, cooldowns and stun — nothing else."""

    x: float
    y: float
    face_x: float = 0.0
    face_y: float = -1.0
    swing_cooldown: float = 0.0
    swing_anim: float = 0.0
    dash: float = 0.0
    dash_cooldown: float = 0.0
    stun: float = 0.0
    invulnerable: float = 0.0
    knock_x: float = 0.0
    knock_y: float = 0.0


@dataclass(slots=True)
class Meta:
    """Progress that survives between nights.  This is the compounding layer."""

    night: int = 1
    attack: int = START_ATTACK
    light: float = START_LIGHT
    max_lives: int = START_LIVES
    sugar: int = 0
    best_night: int = 0


@dataclass(slots=True)
class State:
    """Everything the rules need.  Never holds a pygame object."""

    phase: Phase
    seed: int
    meta: Meta
    player: Player
    lives: int
    action_points: int
    timer: float                    # seconds left in the current phase
    timer_max: float
    villagers: list[Villager] = field(default_factory=list)
    monsters: list[Monster] = field(default_factory=list)
    warnings: list[Warning] = field(default_factory=list)
    drops: list[Drop] = field(default_factory=list)
    traps: list[Trap] = field(default_factory=list)
    elapsed: float = 0.0            # seconds survived this night
    spawn_accumulator: float = 0.0
    surges: list[float] = field(default_factory=list)
    surge_flash: float = 0.0
    fed_count: int = 0
    stopped: int = 0                # total turned villagers stopped
    stopped_by_lantern: int = 0
    stopped_by_trap: int = 0
    reached_sister: int = 0
    sugar_picked: int = 0
    tick: int = 0
    events: list[str] = field(default_factory=list)
    _rng: random.Random = field(default_factory=random.Random, repr=False, compare=False)


# ── helpers ──────────────────────────────────────────────────────────
def clamp(value: float, low: float, high: float) -> float:
    """Return ``value`` constrained to the inclusive interval [low, high]."""
    return max(low, min(high, value))


def distance(ax: float, ay: float, bx: float, by: float) -> float:
    return math.hypot(ax - bx, ay - by)


def circles_touch(ax: float, ay: float, ar: float,
                  bx: float, by: float, br: float) -> bool:
    """Return True when two circles overlap **or touch at exactly one point**.

    Uses squared distance so no square root is needed, and ``<=`` so that
    tangency counts as contact (the course's inclusive-boundary rule).
    """
    dx, dy = ax - bx, ay - by
    reach = ar + br
    return dx * dx + dy * dy <= reach * reach


def night_recipe(night: int) -> list[str]:
    """Return the species list for one night.  Pure and deterministic."""
    total = 5 + min(5, night)
    out: list[str] = []
    for i in range(total):
        if i % 4 == 3:
            out.append("brute")
        elif i % 3 == 2:
            out.append("child")
        else:
            out.append("villager")
    return out


def _surges_for(night: int) -> list[float]:
    """Timestamps where three arrive at once, creating tension spikes."""
    return [14.0, 28.0, 40.0] if night >= 2 else [24.0]


def _build_villagers(night: int) -> list[Villager]:
    """Place the townsfolk around Gretel and stagger when each one turns."""
    kinds = night_recipe(night)
    people: list[Villager] = []
    for i, kind in enumerate(kinds):
        angle = (i / len(kinds)) * math.tau + 0.4
        radius = 190.0 + (i % 3) * 42.0
        people.append(
            Villager(
                kind=kind,
                x=SISTER_X + math.cos(angle) * radius,
                y=SISTER_Y + math.sin(angle) * radius * 0.72,
                wake=1.2 + i * (22.0 / len(kinds)),
            )
        )
    return people


# ── the four contract functions ──────────────────────────────────────
def new_game(seed: int = 0, meta: Meta | None = None) -> State:
    """Return a fresh state with no display or device dependency.

    Interface:
        seed: integer used for every random decision this run.
        meta: optional carried progress; a fresh Meta is used when omitted.
        return: a State in the DAY phase, ready for the first action.

    Invariant: two calls with the same seed and equal meta produce equal
    snapshots.
    """
    carried = deepcopy(meta) if meta is not None else Meta()
    return State(
        phase=Phase.DAY,
        seed=int(seed),
        meta=carried,
        player=Player(x=SISTER_X, y=SISTER_Y + 92.0),
        lives=carried.max_lives,
        action_points=ACTION_POINTS,
        timer=DAY_SECONDS,
        timer_max=DAY_SECONDS,
        villagers=_build_villagers(carried.night),
        surges=_surges_for(carried.night),
        _rng=random.Random(int(seed) + carried.night * 7919),
    )


def is_terminal(state: State) -> bool:
    """Return True only when the documented end rule is met.

    The night ends in exactly two ways: Gretel survives to dawn, or she is
    taken.  Day and night are both in-progress states.
    """
    return state.phase in (Phase.DAWN, Phase.LOST)


def snapshot(state: State) -> dict[str, object]:
    """Return stable, comparable evidence for tests and debugging.

    Floats are rounded so the same run compares equal across platforms.
    """
    return {
        "phase": state.phase.value,
        "seed": state.seed,
        "night": state.meta.night,
        "tick": state.tick,
        "elapsed": round(state.elapsed, 6),
        "timer": round(state.timer, 6),
        "lives": state.lives,
        "action_points": state.action_points,
        "attack": state.meta.attack,
        "light": round(state.meta.light, 3),
        "sugar": state.meta.sugar,
        "player": [round(state.player.x, 3), round(state.player.y, 3)],
        "villagers": len(state.villagers),
        "fed": state.fed_count,
        "monsters": len(state.monsters),
        "awake": sum(1 for m in state.monsters if m.wake <= 0),
        "warnings": len(state.warnings),
        "drops": len(state.drops),
        "traps_unused": sum(1 for t in state.traps if not t.used),
        "stopped": state.stopped,
        "reached": state.reached_sister,
    }


def apply_action(state: State, action: str) -> State:
    """Return the next state **without changing the supplied state**.

    Interface:
        state: the current State (never modified).
        action: one command string, see below.
        return: a new State.

    Accepted actions:
        "tick"                    advance one fixed step with no input
        "move:<dirs>"             advance one step moving; dirs joined by '+'
                                  from up/down/left/right, may add 'swing'
                                  and/or 'dash'  e.g. "move:up+left+swing"
        "swing"                   advance one step swinging in place
        "feed:<index>"            day: share food with villager <index>
        "whet" / "oil"            day: spend one action point on an upgrade
        "trap:<x>,<y>"            day: place a trap at world coordinates
        "begin_night"             day -> night
        "buy:<atk|light|lives>"   dawn/lost: spend sugar on permanent growth
        "next_night"              dawn -> next day (night counter advances)
        "retry"                   lost -> same night again

    Failure path: an unknown action raises ValueError; an action that is not
    legal in the current phase is ignored and the state is returned unchanged
    (a copy), so callers can drive the model from a simple input mapping.
    """
    nxt = deepcopy(state)
    nxt.events = []

    if action == "tick":
        return _step(nxt, set())
    if action == "swing":
        return _step(nxt, {"swing"})
    if action.startswith("move:"):
        return _step(nxt, set(action[5:].split("+")))
    if action.startswith("feed:"):
        return _feed(nxt, int(action[5:]))
    if action in ("whet", "oil"):
        return _day_upgrade(nxt, action)
    if action.startswith("trap:"):
        raw_x, raw_y = action[5:].split(",")
        return _place_trap(nxt, float(raw_x), float(raw_y))
    if action == "begin_night":
        return _begin_night(nxt)
    if action.startswith("buy:"):
        return _buy(nxt, action[4:])
    if action == "next_night":
        return _next_night(nxt)
    if action == "retry":
        return _retry(nxt)

    raise ValueError(f"unknown action: {action!r}")


# ── day actions ──────────────────────────────────────────────────────
def _spend_point(state: State) -> State:
    """Consume one action point and roll into night when they run out."""
    state.action_points -= 1
    if state.action_points <= 0:
        state.events.append("day_over")
    return state


def _feed(state: State, index: int) -> State:
    """Share food with one villager so he hesitates tonight."""
    if state.phase is not Phase.DAY or state.action_points <= 0:
        return state
    if not 0 <= index < len(state.villagers):
        return state
    person = state.villagers[index]
    if person.fed:
        return state
    person.fed = True
    state.fed_count += 1
    state.events.append(f"fed:{index}")
    return _spend_point(state)


def _day_upgrade(state: State, which: str) -> State:
    """Sharpen the lantern or add oil.  Both persist across nights."""
    if state.phase is not Phase.DAY or state.action_points <= 0:
        return state
    if which == "whet":
        state.meta.attack += 1
    else:
        state.meta.light += LIGHT_PER_OIL
    state.events.append(which)
    return _spend_point(state)


def _place_trap(state: State, x: float, y: float) -> State:
    """Set a one-use trap.  Refused too close to Gretel so it cannot be free."""
    if state.phase is not Phase.DAY or state.action_points <= 0:
        return state
    if distance(x, y, SISTER_X, SISTER_Y) < 30.0:
        return state
    state.traps.append(Trap(x=clamp(x, 0, WIDTH), y=clamp(y, 0, HEIGHT)))
    state.events.append("trap")
    return _spend_point(state)


def _begin_night(state: State) -> State:
    """Turn every villager and start the clock."""
    if state.phase is not Phase.DAY:
        return state
    state.phase = Phase.NIGHT
    state.timer = NIGHT_SECONDS
    state.timer_max = NIGHT_SECONDS
    state.elapsed = 0.0
    for person in state.villagers:
        state.monsters.append(_turn(person))
    state.events.append("nightfall")
    return state


def _turn(person: Villager) -> Monster:
    """A fed villager hesitates: one less hit to give and 40% slower."""
    kind = KINDS[person.kind]
    return Monster(
        kind=person.kind,
        x=person.x,
        y=person.y,
        hp=kind.hp - (1 if person.fed else 0),
        speed=kind.speed * (0.6 if person.fed else 1.0),
        fed=person.fed,
        wake=person.wake,
    )


# ── between nights ───────────────────────────────────────────────────
def _buy(state: State, item: str) -> State:
    """Spend sugar on permanent growth.  Only between nights."""
    if not is_terminal(state) or item not in SHOP:
        return state
    cost = SHOP[item][0]
    if state.meta.sugar < cost:
        return state
    state.meta.sugar -= cost
    if item == "atk":
        state.meta.attack += 1
    elif item == "light":
        state.meta.light += LIGHT_PER_OIL
    else:
        state.meta.max_lives += 1
    state.events.append(f"bought:{item}")
    return state


def _next_night(state: State) -> State:
    if state.phase is not Phase.DAWN:
        return state
    carried = deepcopy(state.meta)
    carried.night += 1
    return new_game(state.seed, carried)


def _retry(state: State) -> State:
    if state.phase is not Phase.LOST:
        return state
    return new_game(state.seed, deepcopy(state.meta))


# ── the simulation step ──────────────────────────────────────────────
_DIRECTIONS: Final = {
    "up": (0.0, -1.0),
    "down": (0.0, 1.0),
    "left": (-1.0, 0.0),
    "right": (1.0, 0.0),
}


def _step(state: State, inputs: set[str]) -> State:
    """Advance exactly one fixed time step."""
    if state.phase is Phase.DAY:
        state.tick += 1
        state.timer -= FIXED_DT
        if state.timer <= 0:
            state.timer = 0.0
            state.events.append("day_over")
        return state

    if state.phase is not Phase.NIGHT:
        return state

    dt = FIXED_DT
    state.tick += 1
    state.timer -= dt
    state.elapsed += dt

    _move_player(state, inputs, dt)
    if "swing" in inputs and state.player.stun <= 0:
        _swing(state)

    _spawn(state, dt)
    _advance_monsters(state, dt)
    _collect_drops(state)

    if state.lives <= 0:
        state.phase = Phase.LOST
        state.events.append("lost")
    elif state.timer <= 0:
        state.timer = 0.0
        state.phase = Phase.DAWN
        state.meta.best_night = max(state.meta.best_night, state.meta.night)
        state.events.append("dawn")
    return state


def _move_player(state: State, inputs: set[str], dt: float) -> None:
    p = state.player
    p.swing_cooldown = max(0.0, p.swing_cooldown - dt)
    p.swing_anim = max(0.0, p.swing_anim - dt)
    p.dash = max(0.0, p.dash - dt)
    p.dash_cooldown = max(0.0, p.dash_cooldown - dt)
    p.stun = max(0.0, p.stun - dt)
    p.invulnerable = max(0.0, p.invulnerable - dt)

    # residual knockback keeps pushing even while stunned
    if abs(p.knock_x) + abs(p.knock_y) > 0.5:
        p.x = clamp(p.x + p.knock_x * dt, 16, WIDTH - 16)
        p.y = clamp(p.y + p.knock_y * dt, 16, HEIGHT - 16)
        p.knock_x *= 0.86
        p.knock_y *= 0.86

    if p.stun > 0:
        return

    vx = vy = 0.0
    for name in inputs:
        step = _DIRECTIONS.get(name)
        if step:
            vx += step[0]
            vy += step[1]

    length = math.hypot(vx, vy)
    if length == 0:
        return

    vx /= length
    vy /= length
    p.face_x, p.face_y = vx, vy

    if "dash" in inputs and p.dash_cooldown <= 0:
        p.dash = DASH_TIME
        p.dash_cooldown = DASH_COOLDOWN

    recover = SWING_SLOWDOWN if p.swing_anim > 0 else 1.0
    speed = DASH_SPEED if p.dash > 0 else WALK_SPEED * recover
    p.x = clamp(p.x + vx * speed * dt, 16, WIDTH - 16)
    p.y = clamp(p.y + vy * speed * dt, 16, HEIGHT - 16)


def _swing(state: State) -> None:
    """Swing the lantern in a cone.  Geometry finds targets; this resolves them."""
    p = state.player
    if p.swing_cooldown > 0:
        return
    p.swing_cooldown = SWING_COOLDOWN
    p.swing_anim = SWING_ANIM
    facing = math.atan2(p.face_y, p.face_x)

    survivors: list[Monster] = []
    for m in state.monsters:
        kind = KINDS[m.kind]
        if m.wake > 0:
            survivors.append(m)
            continue
        if distance(m.x, m.y, p.x, p.y) > SWING_RANGE + kind.radius:
            survivors.append(m)
            continue
        angle = math.atan2(m.y - p.y, m.x - p.x)
        offset = abs(((angle - facing + math.pi * 3) % math.tau) - math.pi)
        if offset > SWING_ARC:
            survivors.append(m)
            continue

        m.hp -= state.meta.attack
        m.hit_flash = 0.12
        if kind.knockable:
            m.knockback = 26.0
        if m.hp <= 0:
            state.drops.append(Drop(x=m.x, y=m.y, value=kind.sugar))
            state.stopped += 1
            state.stopped_by_lantern += 1
            state.events.append(f"stopped:{m.kind}")
        else:
            survivors.append(m)

    state.monsters = survivors


def _spawn(state: State, dt: float) -> None:
    """Reinforcements announce their edge before walking in."""
    pool = ["villager", "child", "brute"]
    state.spawn_accumulator += dt

    interval = max(1.4, 4.2 - state.meta.night * 0.4 - state.elapsed * 0.03)
    if state.spawn_accumulator >= interval and state.elapsed > 3:
        state.spawn_accumulator = 0.0
        state.warnings.append(_edge_warning(state, pool))

    if state.surges and state.elapsed >= state.surges[0]:
        state.surges.pop(0)
        state.surge_flash = 1.1
        for _ in range(3):
            state.warnings.append(_edge_warning(state, pool))
    state.surge_flash = max(0.0, state.surge_flash - dt)

    remaining: list[Warning] = []
    for w in state.warnings:
        w.left -= dt
        if w.left > 0:
            remaining.append(w)
            continue
        kind = KINDS[w.kind]
        state.monsters.append(
            Monster(kind=w.kind, x=w.x, y=w.y, hp=kind.hp,
                    speed=kind.speed, fed=False)
        )
    state.warnings = remaining


def _edge_warning(state: State, pool: list[str]) -> Warning:
    side = state._rng.randrange(4)
    if side == 1:
        x, y = WIDTH - 26, 40 + state._rng.random() * (HEIGHT - 80)
    elif side == 3:
        x, y = 26, 40 + state._rng.random() * (HEIGHT - 80)
    elif side == 0:
        x, y = 40 + state._rng.random() * (WIDTH - 80), 26
    else:
        x, y = 40 + state._rng.random() * (WIDTH - 80), HEIGHT - 26
    return Warning(x=x, y=y, kind=state._rng.choice(pool), left=WARN_SECONDS)


def _advance_monsters(state: State, dt: float) -> None:
    """Walk, then resolve trap / player / Gretel contact exactly once each."""
    p = state.player
    survivors: list[Monster] = []

    for m in state.monsters:
        kind = KINDS[m.kind]
        m.hit_flash = max(0.0, m.hit_flash - dt)

        if m.wake > 0:
            m.wake -= dt
            survivors.append(m)
            continue

        dx, dy = SISTER_X - m.x, SISTER_Y - m.y
        d = math.hypot(dx, dy) or 1.0
        if m.knockback > 0:
            step = min(m.knockback, 150.0 * dt)
            m.x -= (dx / d) * step
            m.y -= (dy / d) * step
            m.knockback -= step
        else:
            m.x += (dx / d) * m.speed * dt
            m.y += (dy / d) * m.speed * dt

        # shoving Hansel: costs him control, but he gets brief immunity so a
        # crowd cannot lock him down forever
        if (p.stun <= 0 and p.invulnerable <= 0 and p.dash <= 0
                and circles_touch(m.x, m.y, kind.radius, p.x, p.y, PLAYER_RADIUS)):
            push = distance(p.x, p.y, m.x, m.y) or 1.0
            p.stun = STUN_TIME
            p.invulnerable = INVULNERABLE_TIME
            p.knock_x = (p.x - m.x) / push * KNOCKBACK_SPEED
            p.knock_y = (p.y - m.y) / push * KNOCKBACK_SPEED
            state.events.append("shoved")

        caught = False
        for trap in state.traps:
            if not trap.used and distance(m.x, m.y, trap.x, trap.y) < TRAP_RADIUS:
                trap.used = True
                caught = True
                break
        if caught:
            state.drops.append(Drop(x=m.x, y=m.y, value=kind.sugar))
            state.stopped += 1
            state.stopped_by_trap += 1
            state.events.append("trapped")
            continue

        if math.hypot(SISTER_X - m.x, SISTER_Y - m.y) < SISTER_REACH:
            state.lives -= 1
            state.reached_sister += 1
            state.events.append("reached")
            continue

        survivors.append(m)

    state.monsters = survivors


def _collect_drops(state: State) -> None:
    p = state.player
    remaining: list[Drop] = []
    for drop in state.drops:
        if distance(drop.x, drop.y, p.x, p.y) < 24.0:
            state.meta.sugar += drop.value
            state.sugar_picked += drop.value
            state.events.append("picked")
        else:
            remaining.append(drop)
    state.drops = remaining


# ── convenience for tests and the headless smoke check ───────────────
def run_script(seed: int, actions: list[str], meta: Meta | None = None) -> State:
    """Apply a fixed action list to a fresh game and return the final state."""
    state = new_game(seed, meta)
    for action in actions:
        state = apply_action(state, action)
    return state
