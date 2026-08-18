"""Deterministic randomness.

``random.Random`` is not used anywhere in the rules, for four measured reasons.

**Copying cost.**  ``apply_action`` deep-copies the state every call, and a
Mersenne Twister carries 625 words of state.  Copying it measured 97.5 µs — about
half the total cost of a frame with forty monsters.  This generator is a single
64-bit integer, so copying it is free.

**Snapshot visibility.**  A 625-word state cannot go into a JSON snapshot, so a
run that had silently drawn a different number of random values looked identical
in the evidence.  One integer goes straight in, and a divergence shows up on the
tick it happens.

**Cross-platform agreement.**  This is pure integer arithmetic — no floating
point, no libm, no dependence on CPython's Mersenne Twister implementation — so
the same seed produces the same bytes on macOS, on Linux, and inside the
WebAssembly build.

**Substreams.**  Every purpose draws from its own stream, derived from
``(seed, purpose)``.  That matters because content is going to keep changing:
with one shared stream, adding a monster to the spawn pool shifts every
subsequent draw and invalidates every recorded seed and replay.  With
substreams, changing the spawn table cannot disturb the event roll.

The algorithm is splitmix64 — small, well-tested, and good enough for a game
that needs reproducibility rather than cryptography.
"""

from __future__ import annotations

from dataclasses import dataclass

_MASK = 0xFFFFFFFFFFFFFFFF
_GOLDEN = 0x9E3779B97F4A7C15


def _mix(value: int) -> int:
    """splitmix64's finaliser: scramble an integer into a well-spread one."""
    value = (value + _GOLDEN) & _MASK
    z = value
    z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & _MASK
    z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & _MASK
    return z ^ (z >> 31)


def seed_from(*parts: object) -> int:
    """Derive a 64-bit seed from any combination of values.

    Mixing rather than adding.  The previous scheme was ``seed + night * 7919``,
    which collided 192,486 times across seeds 0–39,999 and nights 1–7 — meaning
    two different nights silently shared one random stream.  Strings are folded
    in byte by byte so purposes can be named in plain text.
    """
    acc = 0xCBF29CE484222325
    for part in parts:
        data = str(part).encode("utf-8")
        for byte in data:
            acc = _mix(acc ^ byte)
        acc = _mix(acc ^ 0xFF)
    return acc & _MASK


@dataclass(slots=True)
class Rng:
    """A seeded stream.  One 64-bit integer of state, copied for free.

    Deliberately has **no default**.  The previous state used
    ``field(default_factory=random.Random)``, which quietly seeded itself from
    operating-system entropy whenever anyone constructed a state without passing
    one — a save-file loader or a test fixture would have looked fine and been
    unreproducible.  Here, forgetting the seed is a TypeError.
    """

    state: int

    def next_u64(self) -> int:
        self.state = (self.state + _GOLDEN) & _MASK
        z = self.state
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & _MASK
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & _MASK
        return z ^ (z >> 31)

    def random(self) -> float:
        """Return a float in [0, 1).

        Built from the top 53 bits so every representable double in the range is
        reachable and the division is exact — no rounding, so the result is
        identical on every platform.
        """
        return (self.next_u64() >> 11) * (2.0 ** -53)

    def below(self, limit: int) -> int:
        """Return an integer in [0, limit).

        Uses Lemire's multiply-shift rather than rejection sampling, so the
        number of words consumed per call is **always exactly one**.  Rejection
        sampling consumes a variable amount — the old code drew between 4 and 16
        words for a single ``randrange(4)`` — and that variability is what makes
        a recorded seed stop reproducing after any unrelated change.
        """
        if limit <= 1:
            return 0
        return (self.next_u64() * limit) >> 64

    def between(self, low: float, high: float) -> float:
        return low + (high - low) * self.random()

    def chance(self, probability: float) -> bool:
        return self.random() < probability

    def pick(self, items):
        """Return one item from a non-empty sequence."""
        return items[self.below(len(items))]

    def weighted(self, pairs) -> str:
        """Return one key from ``(key, weight)`` pairs, by weight.

        Walks the pairs in the order given, so the result depends on the
        sequence's order and not on any dict or set iteration.
        """
        total = 0.0
        for _key, weight in pairs:
            total += max(0.0, weight)
        if total <= 0.0:
            return pairs[0][0]
        roll = self.random() * total
        upto = 0.0
        for key, weight in pairs:
            upto += max(0.0, weight)
            if roll < upto:
                return key
        return pairs[-1][0]

    def fork(self, purpose: str) -> "Rng":
        """Return an independent stream for one purpose.

        The child is derived from this stream's *current* state, so forking is
        reproducible, and drawing from the child never advances the parent.
        """
        return Rng(_mix(self.state ^ seed_from(purpose)))


class Streams:
    """The named substreams a run draws from.

    Each is seeded from ``(seed, night, name)`` and is completely independent of
    the others.  Adding a monster to the spawn pool therefore changes what
    ``spawn`` produces and leaves ``events``, ``loot`` and ``boss`` untouched —
    which is what keeps a recorded seed meaningful while content is still being
    written.
    """

    __slots__ = ("spawn", "events", "loot", "boss", "misc")

    #: Extend this when a new subsystem needs randomness.  Never share a stream
    #: between two subsystems just because it is convenient.
    NAMES = ("spawn", "events", "loot", "boss", "misc")

    def __init__(self, seed: int, night: int) -> None:
        for name in self.NAMES:
            setattr(self, name, Rng(seed_from(seed, night, name)))

    def snapshot(self) -> dict[str, int]:
        """Return every stream position, for the evidence dump."""
        return {name: getattr(self, name).state for name in self.NAMES}
