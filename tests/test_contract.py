"""Focused tests for the four contract functions.

Each test names the rule it protects and states the expected observation
before asserting it.  None of these tests opens a display or presses a key.
"""

from __future__ import annotations

import math

import pytest

from gingerbread import model as m
from gingerbread import apply_action, is_terminal, new_game, snapshot


# ── 1. fresh / restart ───────────────────────────────────────────────
def test_new_game_is_deterministic_for_the_same_seed() -> None:
    """Rule: same seed -> same starting snapshot.

    Expected observation: two independently created games compare equal.
    """
    a = new_game(seed=42)
    b = new_game(seed=42)
    assert snapshot(a) == snapshot(b)


def test_the_seed_does_not_change_the_opening_layout() -> None:
    """Rule: the seed drives reinforcement placement, not the opening layout.

    Expected observation: every snapshot field except 'seed' is identical,
    because villagers are placed by a pure formula, not by the random source.
    """
    a = {k: v for k, v in snapshot(new_game(seed=1)).items() if k != "seed"}
    b = {k: v for k, v in snapshot(new_game(seed=999)).items() if k != "seed"}
    assert a == b


# ── 2. normal action ─────────────────────────────────────────────────
def test_feeding_marks_one_villager_and_spends_one_point() -> None:
    """Rule: sharing food costs one action point and flags exactly one person.

    Expected observation: action_points 4 -> 3, fed 0 -> 1.
    """
    state = new_game(seed=7)
    after = apply_action(state, "feed:0")
    assert after.action_points == 3
    assert after.fed_count == 1
    assert after.villagers[0].fed is True
    assert sum(1 for v in after.villagers if v.fed) == 1


def test_fed_villager_turns_weaker_and_slower() -> None:
    """Rule: a fed villager hesitates — one less hit point and 40% slower.

    Expected observation: after nightfall his hp is base-1 and speed is 0.6x.
    """
    base = m.KINDS["villager"]
    state = new_game(seed=7)
    # villager 0 is a 'villager' by the recipe (index 0 -> not 3 mod 4, not 2 mod 3)
    assert state.villagers[0].kind == "villager"
    state = apply_action(state, "feed:0")
    state = apply_action(state, "begin_night")
    turned = state.monsters[0]
    assert turned.hp == base.hp - 1
    assert turned.speed == pytest.approx(base.speed * 0.6)


# ── 3. boundary and invalid input ────────────────────────────────────
def test_unknown_action_raises_value_error() -> None:
    """Rule: an unknown command is a programming error, not a silent no-op."""
    state = new_game(seed=1)
    with pytest.raises(ValueError):
        apply_action(state, "fly")


def test_out_of_range_feed_index_is_ignored_without_spending_a_point() -> None:
    """Rule: an impossible target must not cost the player anything.

    Expected observation: action_points stays 4 for index -1 and for a huge index.
    """
    state = new_game(seed=1)
    assert apply_action(state, "feed:-1").action_points == 4
    assert apply_action(state, "feed:999").action_points == 4


def test_player_is_clamped_inside_the_playfield_on_every_side() -> None:
    """Rule: the player centre stays within [16, W-16] and [16, H-16] inclusive.

    Expected observation: 400 steps of holding one direction stops exactly on
    the boundary rather than passing it.
    """
    state = apply_action(new_game(seed=1), "begin_night")
    for _ in range(400):
        state = apply_action(state, "move:left+up")
    assert state.player.x == pytest.approx(16.0)
    assert state.player.y == pytest.approx(16.0)

    state = apply_action(new_game(seed=1), "begin_night")
    for _ in range(400):
        state = apply_action(state, "move:right+down")
    assert state.player.x == pytest.approx(m.WIDTH - 16)
    assert state.player.y == pytest.approx(m.HEIGHT - 16)


def test_tangent_circles_count_as_contact() -> None:
    """Rule: touching at exactly one point IS contact (inclusive boundary).

    Expected observation: distance exactly r1+r2 -> True; one unit more -> False.
    """
    assert m.circles_touch(0, 0, 10, 25, 0, 15) is True     # exactly tangent
    assert m.circles_touch(0, 0, 10, 25.001, 0, 15) is False
    assert m.circles_touch(0, 0, 10, 20, 0, 15) is True     # overlapping


# ── 4. terminal rule ─────────────────────────────────────────────────
def test_is_terminal_is_false_during_play_and_true_only_at_an_ending() -> None:
    """Rule: only dawn or loss ends the run; day and night are in progress."""
    state = new_game(seed=3)
    assert is_terminal(state) is False           # day
    state = apply_action(state, "begin_night")
    assert is_terminal(state) is False           # night

    # A well-upgraded run reaches dawn; this also documents that the
    # between-night compounding is what makes survival possible.
    strong = m.Meta(night=1, attack=4, light=140.0, max_lives=6)
    survived = _run_night_to_dawn(seed=3, meta=strong)
    assert survived.phase is m.Phase.DAWN
    assert is_terminal(survived) is True


def test_losing_every_life_ends_the_run_as_lost() -> None:
    """Rule: when Gretel's lives reach zero the phase becomes LOST."""
    state = apply_action(new_game(seed=5), "begin_night")
    for _ in range(int(m.NIGHT_SECONDS / m.FIXED_DT) + 10):
        state = apply_action(state, "tick")     # never defend
        if is_terminal(state):
            break
    assert state.phase is m.Phase.LOST
    assert state.lives == 0


# ── 5. invariant: apply_action must not mutate its input ─────────────
def test_apply_action_never_changes_the_supplied_state() -> None:
    """Rule: apply_action returns a NEW state and leaves the old one intact.

    This is the same contract as advance_body in the Snake lab: the caller's
    object must survive the call untouched.
    """
    state = apply_action(new_game(seed=11), "begin_night")
    before = snapshot(state)
    before_player = (state.player.x, state.player.y)

    for action in ("tick", "move:right", "swing", "move:up+dash"):
        result = apply_action(state, action)
        assert snapshot(state) == before, f"{action} mutated the input state"
        assert (state.player.x, state.player.y) == before_player
        assert result is not state


def test_lives_never_exceed_max_and_never_go_below_zero() -> None:
    """Invariant: 0 <= lives <= meta.max_lives at every observed tick."""
    state = apply_action(new_game(seed=13), "begin_night")
    for _ in range(600):
        state = apply_action(state, "tick")
        assert 0 <= state.lives <= state.meta.max_lives
        if is_terminal(state):
            break


# ── 6. regression: replay determinism ────────────────────────────────
def test_the_same_script_replays_to_the_same_snapshot() -> None:
    """Rule: a fixed seed plus a fixed action list reproduces exactly.

    This is what makes any future failure reproducible.
    """
    script = ["begin_night"] + ["move:right+swing", "tick", "move:up"] * 200
    first = m.run_script(42, script)
    second = m.run_script(42, script)
    assert snapshot(first) == snapshot(second)


def test_snapshot_is_json_safe() -> None:
    """Rule: evidence must survive being written to a file unchanged."""
    import json

    state = apply_action(new_game(seed=8), "begin_night")
    for _ in range(120):
        state = apply_action(state, "move:left+swing")
    text = json.dumps(snapshot(state), sort_keys=True)
    assert json.loads(text) == snapshot(state)


# ── helper ───────────────────────────────────────────────────────────
def _run_night_to_dawn(seed: int, meta: m.Meta | None = None) -> m.State:
    """Play a night with an aggressive scripted defender until it ends."""
    state = new_game(seed=seed, meta=meta)
    for i in range(4):
        state = apply_action(state, f"feed:{i}")
    state = apply_action(state, "begin_night")

    steps = int(m.NIGHT_SECONDS / m.FIXED_DT) + 30
    for _ in range(steps):
        if is_terminal(state):
            break
        state = apply_action(state, _chase_action(state))
    return state


def _chase_action(state: m.State) -> str:
    """Walk toward the awake monster closest to Gretel and swing."""
    awake = [mo for mo in state.monsters if mo.wake <= 0]
    if not awake:
        return "tick"
    target = min(awake, key=lambda mo: math.hypot(mo.x - m.SISTER_X, mo.y - m.SISTER_Y))
    dirs: list[str] = []
    if target.x > state.player.x + 4:
        dirs.append("right")
    elif target.x < state.player.x - 4:
        dirs.append("left")
    if target.y > state.player.y + 4:
        dirs.append("down")
    elif target.y < state.player.y - 4:
        dirs.append("up")
    if not dirs:
        return "swing"
    return "move:" + "+".join(dirs) + "+swing"
