"""The four elements.

Each spell carries one, each boss is answered by one, and matching them is the
difference between chipping and winning.  Kept as a table rather than as an enum
so a fifth element is a row, and so the names can be shown to the player without
a translation layer.

A weakness the player cannot *discover* is only a damage number they never earn,
so every boss announces its element through its phase lines — see
``content/bosses.py``.
"""

from __future__ import annotations

from typing import Final

ELEMENTS: Final[dict[str, dict[str, object]]] = {
    "thunder": {"name": "雷", "colour": (180, 140, 255)},
    "light":   {"name": "光", "colour": (250, 232, 168)},
    "wind":    {"name": "風", "colour": (150, 214, 200)},
    "water":   {"name": "水", "colour": (110, 168, 232)},
}


def name_of(key: str | None) -> str:
    if key is None:
        return "無"
    row = ELEMENTS.get(key)
    return str(row["name"]) if row else key


def colour_of(key: str | None):
    row = ELEMENTS.get(key or "")
    return row["colour"] if row else (200, 200, 200)
