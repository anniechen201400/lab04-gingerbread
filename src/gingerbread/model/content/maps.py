"""The map table.

⚠ **Placeholder content.**  Six maps are sketched from ``遊戲設計定案.md``
v2.0; the real ones come with the boss designs.

The rule this table exists to enforce: **a map must change how the space
plays.**  Six backdrops with identical geometry are one map with six
wallpapers.  Every entry here therefore changes at least one of:

* what blocks movement (obstacles),
* what blocks sight (obstacles that occlude),
* where monsters may enter from (spawn points),
* what is already lit before the player arrives (standing lights).

Coordinates are in world space: 900 × 520, Gretel at (450, 260).
"""

from __future__ import annotations

from typing import Final

from ..specs import MapSpec

MAPS: Final[dict[str, MapSpec]] = {

    # Night 1, the tutorial.  Deliberately featureless: the first night has to
    # teach movement and swinging without any other idea competing for
    # attention.
    "village_square": MapSpec(
        key="village_square", name="村子廣場",
        ground="ground.village_square",
    ),

    # Four mill posts *around* Gretel rather than one wheel on top of her.
    # The original put a 74 px blocker at her exact position, which meant no
    # monster could ever get within her 26 px reach — night two was literally
    # unloseable, and the balance numbers measured from it were meaningless.
    # Sight lines still break constantly; she is still standing in the open.
    "mill": MapSpec(
        key="mill", name="磨坊",
        obstacles=(
            (450.0, 118.0, 52.0, True),
            (450.0, 448.0, 46.0, True),
            (256.0, 260.0, 44.0, True),
            (644.0, 260.0, 44.0, True),
        ),
        lights=((450.0, 92.0, 70.0),),
        ground="ground.mill",
    ),

    # Scattered trunks: movement stays mostly open but nothing can be watched
    # for long, which is what makes the ranged threat land.
    "forest_edge": MapSpec(
        key="forest_edge", name="森林邊緣",
        obstacles=(
            (168.0, 122.0, 34.0, True),
            (712.0, 148.0, 30.0, True),
            (236.0, 402.0, 32.0, True),
            (664.0, 386.0, 36.0, True),
            (452.0, 74.0, 26.0, True),
        ),
        ground="ground.forest_edge",
    ),

    # Stalls funnel every arrival through four gaps.  The player can finally
    # hold a line — and the night punishes him for holding the wrong one.
    "market": MapSpec(
        key="market", name="市集",
        obstacles=(
            (150.0, 190.0, 46.0, True),
            (750.0, 190.0, 46.0, True),
            (150.0, 330.0, 46.0, True),
            (750.0, 330.0, 46.0, True),
            (450.0, 96.0, 40.0, True),
            (450.0, 424.0, 40.0, True),
        ),
        spawn_points=((26.0, 260.0), (874.0, 260.0),
                      (450.0, 26.0), (450.0, 494.0)),
        ground="ground.market",
    ),

    # Wide open, but three standing candles mean the player is never fully
    # blind — which is exactly why losing the lantern here is survivable.
    "chapel": MapSpec(
        key="chapel", name="教堂",
        lights=((190.0, 150.0, 86.0),
                (710.0, 150.0, 86.0),
                (450.0, 430.0, 86.0)),
        ground="ground.chapel",
    ),

    # Cramped: hooks everywhere, nowhere to retreat to.  Every fight is at
    # arm's length.
    "butchery": MapSpec(
        key="butchery", name="肉舖",
        obstacles=(
            (300.0, 160.0, 30.0, False),
            (600.0, 160.0, 30.0, False),
            (300.0, 360.0, 30.0, False),
            (600.0, 360.0, 30.0, False),
            (450.0, 130.0, 26.0, False),
            (450.0, 452.0, 26.0, False),
        ),
        ground="ground.butchery",
    ),

    # The place they were abandoned.  Largest and emptiest on purpose: the
    # final night should feel like nowhere is safe rather than like a corridor.
    "deep_forest": MapSpec(
        key="deep_forest", name="森林深處",
        obstacles=(
            (120.0, 100.0, 28.0, True),
            (780.0, 110.0, 28.0, True),
            (110.0, 420.0, 28.0, True),
            (790.0, 410.0, 28.0, True),
            (300.0, 260.0, 24.0, True),
            (600.0, 260.0, 24.0, True),
        ),
        ground="ground.deep_forest",
    ),
}

#: Endless mode cycles these, changing map every few minutes so a long run does
#: not become one unchanging room.
ENDLESS_ROTATION: Final[tuple[str, ...]] = (
    "village_square", "mill", "forest_edge", "market", "chapel", "butchery",
)
