"""Spell and night-event resolvers.

Registered by name, the same way monster behaviours are, so a new skill is a row
in ``content/spells.py`` plus — usually — nothing here at all, because an
existing resolver already does the job with different numbers.

Everything draws from a named substream and never from ``random``.
"""

from __future__ import annotations

import math

from . import constants as C
from . import geometry as g
from .content.monsters import MONSTERS
from .entities import Drop, Effect, Hazard, Monster, Puddle
from .registry import event, spell
from .state import State


def _targets(state: State):
    """Everything a skill may act on: awake, above ground, on the field.

    Buried monsters are excluded on purpose — that is the digger's whole point,
    and the reason a player who has been clearing with lightning has to walk
    back and stand guard instead.
    """
    return [x for x in list(state.monsters) + list(state.bosses)
            if x.awake and x.buried <= 0]


# ── skills ───────────────────────────────────────────────────────────
@spell("smite", label="劈擊", note="以玩家為中心，範圍內全部受傷並被擊退")
def smite(state: State, spec) -> None:
    """雷 · 閃電 — the clear-the-board answer.

    Centred on the player rather than on the field, so it rewards standing in
    the crowd: the panic button is also a positioning decision.
    """
    from .rules import damage_target

    radius = float(spec.params.get("radius", 260.0))
    power = int(spec.params.get("damage", 4))
    push = float(spec.params.get("push", 90.0))

    for target in _targets(state):
        if g.distance(target.x, target.y,
                      state.player.x, state.player.y) > radius:
            continue
        # Thrown outward from the player, who is standing in the middle of it.
        damage_target(state, target, power, element=spec.element,
                      from_x=state.player.x, from_y=state.player.y)
        from .rules import _push
        _push(target, state.player.x, state.player.y, push)

    state.effects.append(Effect("bolt", state.player.x, state.player.y,
                                0.35, 0.35, radius))
    state.feedback.bump(shake=float(spec.params.get("shake", 12.0)), freeze=0.08)


@spell("reveal_all", label="照明", note="一段時間內照亮全場，隱形的東西現形")
def reveal_all(state: State, spec) -> None:
    """光 · 聖光 — detection, not damage.

    The only skill that changes what the player can *see* rather than what is on
    the field, which is why it is the answer to a whole category of monster
    instead of to a number.
    """
    state.reveal_ticks = max(1, int(round(spec.duration / C.FIXED_DT)))
    for target in _targets(state):
        target.faded = 0.0
        if getattr(target, "weakness", None) == "light":
            target.memory["exposed"] = C.WEAKNESS_WINDOW
    state.effects.append(Effect("holy", C.SISTER_X, C.SISTER_Y, 0.6, 0.6, 760))
    state.feedback.bump(shake=float(spec.params.get("shake", 3.0)))
    _expose_matching(state, spec)


@spell("twister", label="龍捲風",
       note="往面對的方向放出一道龍捲風，沿路的怪被捲起來一起帶走",
       params={"speed": (150.0, "每秒前進幾像素"),
               "radius": (52.0, "捲得到多寬"),
               "hold": (2.5, "被放下之後還昏多久")})
def twister(state: State, spec) -> None:
    """風 · 龍捲風 — position control you have to aim.

    The first version teleported every awake monster to the map edge, which
    made it lightning without the damage: one key that answered the whole
    field, from anywhere, with no decision in it.  A funnel that travels in one
    direction asks *which* direction — which is the only question a control
    skill should be asking.

    It leaves along a straight line and does not care about scenery.  Whatever
    it catches rides with it and is put down wherever the wind gave out.
    """
    p = state.player
    dx, dy = g.normalise(p.face_x, p.face_y)
    if dx == 0.0 and dy == 0.0:
        dx, dy = 1.0, 0.0
    speed = float(spec.params.get("speed", 150.0))
    radius = float(spec.params.get("radius", 52.0))
    # Born a step in front of him, not on top of him: spawning it at his feet
    # caught whatever was already hitting him, which made it a panic button
    # again instead of a thing he aims.
    state.hazards.append(Hazard(
        kind="twister", x=p.x + dx * 36.0, y=p.y + dy * 36.0,
        radius=radius, life=float(spec.duration),
        vx=dx * speed, vy=dy * speed,
        hold=float(spec.params.get("hold", 2.5))))
    state.effects.append(Effect("tornado", p.x, p.y, 0.5, 0.5, 120))
    state.feedback.bump(shake=float(spec.params.get("shake", 8.0)))
    _expose_matching(state, spec)


@spell("trap", label="水牢",
       note="在腳下放一顆水泡，踩到的怪會被關進去",
       params={"hold": (5.0, "關住幾秒"),
               "radius": (34.0, "水泡多大"),
               "catches": (1.0, "能關住幾隻")})
def water_trap(state: State, spec) -> None:
    """水 · 水牢 — a trap, which means it is placed before it is needed.

    It used to seize the monster nearest Gretel the moment it was cast, so it
    played itself: there was never a wrong time to press it and never a place
    worth standing.  A bubble left on the ground turns the same five seconds
    into a question about *where the next one will walk*, which is the only
    interesting question this game's field can ask.

    It glows — see ``lights_of``.  A trap you cannot find again is not a plan.
    """
    p = state.player
    state.hazards.append(Hazard(
        kind="bubble", x=p.x, y=p.y,
        radius=float(spec.params.get("radius", 34.0)),
        life=float(spec.duration),
        hold=float(spec.params.get("hold", 5.0)),
        charges=float(spec.params.get("catches", 1.0))))
    # Water washes the ground clean, which is the fire boss's whole answer.
    state.puddles = [pool for pool in state.puddles if pool.burn <= 0]
    state.effects.append(Effect("cage", p.x, p.y, 0.5, 0.5, 34))
    state.feedback.bump(shake=float(spec.params.get("shake", 2.0)))
    _expose_matching(state, spec)


def _expose_matching(state: State, spec) -> None:
    """Open a damage window on anything this element answers.

    A weakness that only multiplied the spell's own damage would be worth using
    once; opening a window means the *lantern* gets the payoff, so the skill is
    a setup and the fight stays a fight.
    """
    from .content import BOSSES

    for target in list(state.bosses) + list(state.monsters):
        if target in state.bosses:
            row = BOSSES.get(target.spec)
        else:
            row = MONSTERS.get(target.spec)
        weak = row.weakness if row else None
        if weak is not None and weak == spec.element:
            target.memory["exposed"] = C.WEAKNESS_WINDOW
            state.effects.append(Effect("exposed", target.x, target.y, 0.5, 0.5))
            state.emit(f"exposed:{target.spec}")


# ── night events ─────────────────────────────────────────────────────
@event("dim", label="變暗", note="縮小所有光源")
def dim(state: State, spec) -> None:
    state.light_scale = float(spec.params.get("factor", 0.7))


@event("reveal", label="月光", note="短暫照亮全場，但不會定住怕光的東西")
def reveal(state: State, spec) -> None:
    state.reveal_ticks = max(1, int(round(spec.duration / C.FIXED_DT)))


@event("douse", label="熄燈", note="提燈直接熄掉一段時間")
def douse(state: State, spec) -> None:
    state.player.doused = max(state.player.doused, spec.duration)


@event("hush", label="死寂", note="一段時間內不生新的敵人")
def hush(state: State, spec) -> None:
    state.hush_ticks = max(1, int(round(spec.duration / C.FIXED_DT)))


@event("spawn_burst", label="一擁而上", note="一次生出一群",
       params={"count": (5.0, "生幾隻")})
def spawn_burst(state: State, spec) -> None:
    from .rules import add_warning

    for _ in range(int(spec.params.get("count", 5))):
        x, y = g.edge_point(state.streams.events)
        add_warning(state, "child", x, y, surge=True)


@event("sugar_burst", label="糖霜雨", note="場上隨機掉一堆糖霜",
       params={"count": (8.0, "掉幾顆")})
def sugar_burst(state: State, spec) -> None:
    stream = state.streams.events
    for _ in range(int(spec.params.get("count", 8))):
        state.drops.append(Drop(x=stream.between(60.0, C.WIDTH - 60.0),
                                y=stream.between(60.0, C.HEIGHT - 60.0),
                                value=1))
