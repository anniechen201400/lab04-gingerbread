"""Guards on the content layer.

These exist because content is being written by several people over time.  Each
one protects a rule that is easy to break by accident and impossible to notice
by reading a diff — a misspelled trait silently does nothing, a monster that
splits into itself spawns forever, and a behaviour that calls ``random``
destroys the determinism contract without any visible symptom until the graded
``--check`` run disagrees with itself.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from gingerbread import model as m
from gingerbread.model import registry
from gingerbread.model.content import (BOSSES, EVENTS, MAPS, MONSTERS, SPELLS,
                                       STAGES, check)
from gingerbread.model.content.monsters import ENDLESS_POOL
from gingerbread.model.content.upgrades import ENDLESS_OFFER, SHOP_ORDER, UPGRADES

MODEL_DIR = pathlib.Path(m.__file__).parent


def test_the_shipped_content_validates() -> None:
    """Every cross-reference in every table resolves."""
    check()


def test_every_monster_names_a_registered_behaviour_and_traits() -> None:
    known_traits = {name for hook in registry.HOOKS for name in registry.TRAITS[hook]}
    for key, spec in MONSTERS.items():
        assert spec.behaviour in registry.BEHAVIOURS, f"{key}: {spec.behaviour}"
        for trait in spec.traits:
            assert trait in known_traits, f"{key}: {trait}"


def test_no_monster_can_spawn_itself_directly_or_indirectly() -> None:
    """A split loop is an unkillable fountain that eventually eats the frame rate.

    Each row looks fine on its own, which is what makes it worth a test.
    """
    for key, spec in MONSTERS.items():
        seen, current = set(), key
        while current is not None and current not in seen:
            seen.add(current)
            current = MONSTERS[current].params.get("split_into") if current in MONSTERS else None
            current = str(current) if current is not None else None
        assert current is None, f"{key} spawns in a loop"


def test_boss_phases_descend_and_reach_zero() -> None:
    """A boss whose last phase stops above zero cannot be killed."""
    for key, boss in BOSSES.items():
        assert boss.phases, key
        thresholds = [phase.until_hp for phase in boss.phases]
        assert thresholds == sorted(thresholds, reverse=True), key
        assert thresholds[-1] == 0.0, f"{key} becomes invulnerable below {thresholds[-1]}"


def test_no_boss_behaviour_walks_straight_at_gretel() -> None:
    """Design rule: a boss that charges her is a health bar, not a fight."""
    for key, boss in BOSSES.items():
        assert boss.phases[0].behaviour != "charge", (
            f"{key}'s opening phase charges Gretel; give it an approach")


def test_every_stage_uses_a_real_map_and_cast() -> None:
    for night, stage in STAGES.items():
        assert stage.map_key in MAPS
        assert all(name in MONSTERS for name in stage.recipe)
        if stage.boss:
            assert stage.boss in BOSSES


def test_night_one_has_no_boss_and_no_event() -> None:
    """The tutorial teaches one idea; a twist on top buries the idea.

    Expressed as data — night 1's events are gated by each event's own
    ``min_night`` — so a designer can move it without editing the engine.
    """
    assert STAGES[1].boss is None
    assert all(spec.min_night >= 2 for spec in EVENTS.values())


def test_shop_and_endless_offers_name_real_upgrades() -> None:
    for key in SHOP_ORDER + ENDLESS_OFFER:
        assert key in UPGRADES, key
    for key, _weight in ENDLESS_POOL:
        assert key in MONSTERS, key


def test_upgrade_caps_are_reachable_and_priced() -> None:
    for key, spec in UPGRADES.items():
        assert spec.max_level >= 1, key
        if not spec.consumable:
            assert spec.base_cost > 0, f"{key} is permanent but free"


def test_every_shop_upgrade_is_permanent_except_healing() -> None:
    """Rule: the day sells growth that lasts, and exactly one consumable.

    A shop that mixes permanent and temporary purchases at the same prices asks
    the player to remember which is which, forever, for no gain.
    """
    for key in SHOP_ORDER:
        spec = UPGRADES[key]
        if spec.consumable:
            assert key == "mend", f"{key} is consumable but is not the heal"
        else:
            assert spec.base_cost > 0, f"{key} is permanent but free"


# ── the determinism guard ────────────────────────────────────────────
def _rules_modules() -> list[pathlib.Path]:
    return sorted(p for p in MODEL_DIR.rglob("*.py"))


def test_no_rules_module_imports_pygame() -> None:
    """The rules must stay simulatable with no display, or --check is worthless."""
    for path in _rules_modules():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            assert not any(n.split(".")[0] == "pygame" for n in names), (
                f"{path.name} imports pygame")


def test_no_rules_module_uses_the_random_module() -> None:
    """Every roll must go through ``state.streams``.

    A single ``random.random()`` in a contributed behaviour silently breaks
    "same seed, same result" and nothing else in the project notices until the
    graded determinism check disagrees with its own previous output.
    """
    offenders: list[str] = []
    for path in _rules_modules():
        if path.name == "rng.py":
            continue                      # the generator itself is allowed
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                if any(a.name.split(".")[0] == "random" for a in node.names):
                    offenders.append(f"{path.name}: import random")
            elif isinstance(node, ast.ImportFrom):
                if (node.module or "").split(".")[0] == "random":
                    offenders.append(f"{path.name}: from random import ...")
    assert not offenders, "; ".join(offenders)


def test_no_rules_module_reads_a_clock() -> None:
    """Wall-clock reads make a replay depend on when it was run."""
    banned = {"time", "datetime"}
    for path in _rules_modules():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                names = {(node.module or "").split(".")[0]}
            else:
                continue
            assert not (names & banned), f"{path.name} imports a clock"


def test_the_swing_cone_constants_match_the_documented_angle() -> None:
    """The cone is defined by hard-coded cosine and sine, not by calling libm.

    Platform trig differs in the last bit, and a one-ULP change was measured to
    alter the outcome of 64 of 72 simulated nights.  This pins the literals to
    the angle they claim to represent, so editing one without the other fails.
    """
    import math

    from gingerbread.model import geometry as g

    assert g.ARC_COS == pytest.approx(math.cos(m.constants.SWING_ARC), abs=1e-15)
    assert g.ARC_SIN == pytest.approx(math.sin(m.constants.SWING_ARC), abs=1e-15)


def test_content_check_reports_every_problem_at_once() -> None:
    """A validator that stops at the first error makes fixing a table miserable."""
    from gingerbread.model.registry import validate_names

    with pytest.raises(LookupError) as caught:
        validate_names([("row A", "nope_behaviour", ("nope_trait",), {}),
                        ("row B", "also_missing", (), {})])
    message = str(caught.value)
    assert "row A" in message and "row B" in message


def test_gretel_can_always_be_reached() -> None:
    """Regression: two maps shipped with a blocker centred on Gretel.

    She never moves, so an obstacle on her spot means no monster can ever get
    within her reach — the night looks normal and simply cannot be lost, and
    every balance number measured from it is fiction.
    """
    import math

    from gingerbread.model.content import _gretel_is_reachable

    assert _gretel_is_reachable() == []

    smallest = min(spec.radius for spec in MONSTERS.values())
    for key, spec in MAPS.items():
        for ox, oy, orad, _occ in spec.obstacles:
            gap = math.hypot(ox - m.SISTER_X, oy - m.SISTER_Y)
            assert gap >= orad + m.constants.SISTER_REACH + smallest, (
                f"map {key!r} walls Gretel off")
