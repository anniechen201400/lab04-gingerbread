"""The night-event table.

⚠ **Placeholder content.**  Six events sketched from ``遊戲設計定案.md`` v2.0.

Events exist so two runs of the same night are not the same night.  One is
drawn per night from night two onward — the tutorial stays clean.

Every event is **announced**.  An unexplained change to the rules mid-night is
indistinguishable from a bug, and a player who thinks the game is broken stops
trying to read it.
"""

from __future__ import annotations

from typing import Final

from ..specs import EventSpec

EVENTS: Final[dict[str, EventSpec]] = {

    "snow": EventSpec(
        key="snow", name="大雪", description="看不遠了",
        duration=15.0, effect="dim", params={"factor": 0.7},
    ),

    "moonlight": EventSpec(
        key="moonlight", name="月光", description="你看得見所有人",
        duration=10.0, effect="reveal", params={},
        weight=0.7,
    ),

    "crying": EventSpec(
        key="crying", name="飢餓的哭聲", description="孩子從四面八方來",
        duration=0.1, effect="spawn_burst",
        params={"count": 5.0}, min_night=3,
    ),

    "blackout": EventSpec(
        key="blackout", name="燈滅了", description="三秒內什麼都看不見",
        duration=3.0, effect="douse", params={},
        min_night=4, weight=0.8,
    ),

    "sugarfall": EventSpec(
        key="sugarfall", name="糖霜雨", description="地上突然多了很多糖霜",
        duration=0.1, effect="sugar_burst",
        params={"count": 8.0}, weight=0.6,
    ),

    "hush": EventSpec(
        key="hush", name="死寂", description="二十秒內沒有人來",
        duration=20.0, effect="hush", params={},
        weight=0.5,
    ),
}
