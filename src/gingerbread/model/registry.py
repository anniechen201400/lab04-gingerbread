"""Name-to-function registries, and the validation that keeps content honest.

Content tables refer to code by name: a monster row says ``behaviour="charge"``
and ``traits=("armoured",)``.  This module binds those names to real functions,
catches typos, and — because every entry declares its own parameters and a plain
description — **generates the codex** instead of anyone maintaining one by hand.

That last part is the whole design.  A bestiary written separately from the code
is wrong within a month: someone retunes a number, nobody edits the wiki, and
the document quietly becomes fiction.  Here the description of what a monster
does is derived from the same rows the simulation reads, so it cannot drift.

Adding a mechanic
-----------------
::

    @trait("armoured", "hurt",
           label="盔甲",
           note="要先打掉護甲才能傷到本體",
           params={"armour": (2, "護甲點數")})
    def armoured(state, monster, payload=0.0): ...

The ``params`` mapping is simultaneously the default values, the documentation,
and the validator: a row that writes ``armor=3`` fails at import with a message
naming the row and the correct spelling.
"""

from __future__ import annotations

import difflib
from typing import Callable, Final, Iterable, Mapping, Protocol, TYPE_CHECKING

if TYPE_CHECKING:                      # pragma: no cover - typing only
    from .entities import Monster
    from .state import State


#: The fixed moments a trait may attach to.  Deliberately small: every hook is a
#: promise the rules must keep calling, so the set only grows when a real piece
#: of content cannot be expressed without it.
HOOKS: Final = (
    "spawn",           # the moment it enters the world
    "tick",            # every simulation step while it is awake
    "hurt",            # it took damage but survived
    "death",           # it was removed by damage
    "touch_player",    # it made contact with Hansel
    "reach_sister",    # it got to Gretel
)


class Behaviour(Protocol):
    """How a monster decides where to go this tick.

    Implementations mutate ``monster`` in place and may read the whole state.
    They must not read a clock and must take every random decision through
    ``state.streams`` — a behaviour that calls ``random.random()`` silently
    breaks replay determinism, and nothing else in the project will notice.
    """

    def __call__(self, state: "State", monster: "Monster", dt: float) -> None: ...


class Trait(Protocol):
    """A reaction bound to one hook.  Traits compose; order follows the row."""

    def __call__(self, state: "State", monster: "Monster",
                 payload: float = 0.0) -> None: ...


class Entry:
    """One registered function plus everything the codex needs to describe it."""

    __slots__ = ("name", "fn", "kind", "hook", "label", "note", "params")

    def __init__(self, name: str, fn, kind: str, hook: str | None,
                 label: str, note: str,
                 params: Mapping[str, tuple[float, str]]) -> None:
        self.name = name
        self.fn = fn
        self.kind = kind
        self.hook = hook
        self.label = label or name
        self.note = note
        self.params = dict(params)

    def defaults(self) -> dict[str, float]:
        return {key: value for key, (value, _doc) in self.params.items()}


BEHAVIOURS: Final[dict[str, Entry]] = {}
TRAITS: Final[dict[str, dict[str, Entry]]] = {hook: {} for hook in HOOKS}
SPELLS: Final[dict[str, Entry]] = {}
EVENTS: Final[dict[str, Entry]] = {}

#: Every trait name, whatever hook it lives on — used for lookup and validation.
TRAIT_INDEX: Final[dict[str, list[Entry]]] = {}


def behaviour(name: str, *, label: str = "", note: str = "",
              params: Mapping[str, tuple[float, str]] | None = None):
    """Register a movement behaviour under ``name``."""

    def register(fn):
        if name in BEHAVIOURS:
            raise ValueError(f"behaviour {name!r} is already registered")
        BEHAVIOURS[name] = Entry(name, fn, "behaviour", None,
                                 label, note, params or {})
        return fn

    return register


def trait(name: str, hook: str, *, label: str = "", note: str = "",
          params: Mapping[str, tuple[float, str]] | None = None):
    """Register a trait that fires at ``hook``.

    The same name may appear under several hooks — a monster that both burrows
    (tick) and bursts (death) registers twice and reads as one idea in the table.
    """
    if hook not in TRAITS:
        raise ValueError(f"unknown hook {hook!r}; expected one of {HOOKS}")

    def register(fn):
        if name in TRAITS[hook]:
            raise ValueError(f"trait {name!r} already registered for {hook!r}")
        entry = Entry(name, fn, "trait", hook, label, note, params or {})
        TRAITS[hook][name] = entry
        TRAIT_INDEX.setdefault(name, []).append(entry)
        return fn

    return register


def spell(name: str, *, label: str = "", note: str = "",
          params: Mapping[str, tuple[float, str]] | None = None):
    def register(fn):
        if name in SPELLS:
            raise ValueError(f"spell effect {name!r} is already registered")
        SPELLS[name] = Entry(name, fn, "spell", None, label, note, params or {})
        return fn
    return register


def event(name: str, *, label: str = "", note: str = "",
          params: Mapping[str, tuple[float, str]] | None = None):
    def register(fn):
        if name in EVENTS:
            raise ValueError(f"event effect {name!r} is already registered")
        EVENTS[name] = Entry(name, fn, "event", None, label, note, params or {})
        return fn
    return register


# ── dispatch ─────────────────────────────────────────────────────────
def run_behaviour(name: str, state: "State", monster: "Monster",
                  dt: float) -> None:
    """Run one behaviour by name, falling back to ``charge`` if it is unknown."""
    entry = BEHAVIOURS.get(name) or BEHAVIOURS.get("charge")
    if entry is not None:
        entry.fn(state, monster, dt)


def fire_traits(hook: str, names: Iterable[str], state: "State",
                monster: "Monster", payload: float = 0.0) -> None:
    """Fire every trait in ``names`` registered for ``hook``.

    Names with no entry at this hook are skipped silently — that is the normal
    case, since a trait usually attaches to only one of the six.
    """
    table = TRAITS[hook]
    for name in names:
        entry = table.get(name)
        if entry is not None:
            entry.fn(state, monster, payload)


def param(spec, entry_name: str, key: str, fallback: float = 0.0) -> float:
    """Read one parameter for a spec, falling back to the declared default.

    Going through the declaration rather than a bare ``spec.params.get`` means a
    balance change to a default reaches every row that did not override it.
    """
    if key in getattr(spec, "params", {}):
        return float(spec.params[key])
    for source in (BEHAVIOURS.get(entry_name), *TRAIT_INDEX.get(entry_name, ())):
        if source is not None and key in source.params:
            return float(source.params[key][0])
    return fallback


# ── validation ───────────────────────────────────────────────────────
def _suggest(name: str, known: Iterable[str]) -> str:
    close = difflib.get_close_matches(name, list(known), n=1)
    return f"（是不是 {close[0]!r}？）" if close else ""


def validate_names(rows: Iterable[tuple[str, str, Iterable[str], Mapping]]) -> None:
    """Check every row names something real and passes only known parameters.

    Collects **all** problems and raises once.  Fixing a content table one crash
    at a time is miserable, and someone who has just renamed a monster wants the
    whole blast radius in a single message.
    """
    problems: list[str] = []

    for row_id, behaviour_name, trait_names, params in rows:
        known_params: set[str] = set()

        entry = BEHAVIOURS.get(behaviour_name)
        if entry is None:
            problems.append(f"{row_id}：沒有這個行為 {behaviour_name!r}"
                            f"{_suggest(behaviour_name, BEHAVIOURS)}")
        else:
            known_params |= set(entry.params)

        for name in trait_names:
            entries = TRAIT_INDEX.get(name)
            if not entries:
                problems.append(f"{row_id}：沒有這個特性 {name!r}"
                                f"{_suggest(name, TRAIT_INDEX)}")
                continue
            for one in entries:
                known_params |= set(one.params)

        # ``split_into`` names another monster rather than tuning a behaviour,
        # and the content checker validates it separately.
        known_params.add("split_into")

        # Unknown parameter names are the silent killer: the row looks tuned,
        # the value is simply never read, and the monster behaves like default.
        for key in params or {}:
            if key not in known_params:
                problems.append(
                    f"{row_id}：參數 {key!r} 沒有任何行為或特性會讀取"
                    f"{_suggest(key, known_params)}")

    if problems:
        raise LookupError("內容表引用了不存在的名稱：\n  " + "\n  ".join(problems))


# ── the codex ────────────────────────────────────────────────────────
def describe_mechanic(name: str) -> str:
    """Return the plain-language line for one behaviour or trait name."""
    entry = BEHAVIOURS.get(name)
    if entry is not None:
        return f"{entry.label}：{entry.note}" if entry.note else entry.label
    entries = TRAIT_INDEX.get(name) or []
    if not entries:
        return name
    first = entries[0]
    return f"{first.label}：{first.note}" if first.note else first.label


def vocabulary() -> str:
    """Return every registered name, for ``python -m gingerbread --content``.

    This is the list a content author works from.  Printing it from the registry
    rather than from a document means it is never out of date.
    """
    lines = ["行為（每隻怪選一個）："]
    for name, entry in sorted(BEHAVIOURS.items()):
        lines.append(f"  {name:<14} {entry.label} — {entry.note}")
        for key, (value, doc) in sorted(entry.params.items()):
            lines.append(f"      {key} = {value}   {doc}")

    lines.append("")
    lines.append("特性（可以疊加幾個都行）：")
    for name in sorted(TRAIT_INDEX):
        for entry in TRAIT_INDEX[name]:
            lines.append(f"  {name:<14} {entry.label} — {entry.note}"
                         f"   [{entry.hook}]")
            for key, (value, doc) in sorted(entry.params.items()):
                lines.append(f"      {key} = {value}   {doc}")

    lines.append("")
    lines.append("法術效果：" + "、".join(sorted(SPELLS)))
    lines.append("夜晚事件：" + "、".join(sorted(EVENTS)))
    return "\n".join(lines)
