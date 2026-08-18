"""The skill codex.

Four skills, one per element, from the design document.  Each has a *job* rather
than a damage number — 清場 / 偵測 / 控位置 / 控單體 — because four skills that
all mean "deal damage" would only differ in how much, and the player would carry
the biggest one.

A skill is **learned once and then always available**, gated only by a
cooldown.  One skill point arrives each day, so the campaign hands out one new
skill per night survived.  Charges were the first design and they were wrong:
a stock turns every cast into "am I allowed to spend this yet", which is exactly
the wrong feeling for a panic button.  A cooldown asks *when*, which is a
question about the fight in front of you.

Two are carried at a time, so the choice of which is made in daylight.

Elements matter twice: a skill hits the thing it answers for
``WEAKNESS_MULTIPLIER`` damage, and on a boss it opens a window where everything
hurts more.  That is what turns "which skill do I bring" into a question with a
right answer the player has to have learned.
"""

from __future__ import annotations

from typing import Final

from ..specs import SpellSpec

SPELLS: Final[dict[str, SpellSpec]] = {

    "bolt": SpellSpec(
        key="bolt", name="閃電", element="thunder",
        description="以自己為中心劈下閃電，範圍內全部受傷並被擊退",
        # Was radius 260 / damage 4 / 20 s.  At those numbers it cleared the
        # whole field on a cooldown short enough to have back before the field
        # refilled, so the other three skills were only ever "lightning is not
        # up yet".  Now it clears what is *around him* — position still matters
        # — and there is a real gap to survive afterwards.
        cost=1, cooldown=27.0, duration=0.0,
        effect="smite",
        params={"radius": 185.0, "damage": 3.0, "push": 70.0, "shake": 12.0},
        colour=(180, 140, 255)),

    "holy": SpellSpec(
        key="holy", name="聖光", element="light",
        description="八秒內照亮全場，隱形的東西全部現形",
        cost=1, cooldown=22.0, duration=8.0,
        effect="reveal_all",
        params={"shake": 3.0},
        colour=(250, 232, 168)),

    "tornado": SpellSpec(
        key="tornado", name="龍捲風", element="wind",
        description="朝面對的方向放出龍捲風，捲起沿路的怪一起帶走",
        cost=1, cooldown=16.0, duration=5.0,
        effect="twister",
        params={"speed": 150.0, "radius": 52.0, "hold": 2.5, "shake": 8.0},
        colour=(150, 214, 200)),

    "cage": SpellSpec(
        key="cage", name="水牢", element="water",
        # ``duration`` is how long the bubble waits, not how long it holds —
        # ``hold`` is that.  A trap's lifetime and its grip are different
        # numbers and the skill only makes sense when they are.
        description="在腳下放一顆水泡，踩到的怪會被關住五秒",
        cost=1, cooldown=11.0, duration=14.0,
        effect="trap",
        params={"hold": 5.0, "radius": 34.0, "catches": 1.0, "shake": 2.0},
        needs_target=False,
        colour=(110, 168, 232)),
}
