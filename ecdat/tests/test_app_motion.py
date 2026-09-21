"""Tests for the pure motion helpers in :mod:`ecdat.ui.motion`.

These cover the env-resolution matrix for :func:`animations_enabled`, the
deterministic scramble/count-up helpers, and the adaptive :class:`FrameBudget`.
"""

from __future__ import annotations

import pytest

from ecdat.ui.motion import (
    FrameBudget,
    animations_enabled,
    clamp01,
    count_up_value,
    ease_out_cubic,
    scramble,
)


# ---- animations_enabled ---------------------------------------------------


@pytest.mark.parametrize("value", ["0", "off", "false", "no", "OFF", "False", "NO"])
def test_anim_off_variants(value: str) -> None:
    assert animations_enabled(env={"ECDAT_ANIM": value}) is False


@pytest.mark.parametrize("value", ["1", "on", "true", "yes", "ON", "Yes"])
def test_anim_on_variants(value: str) -> None:
    assert animations_enabled(env={"ECDAT_ANIM": value}) is True


def test_anim_default_on() -> None:
    assert animations_enabled(env={}) is True


def test_reduce_motion_disables() -> None:
    assert animations_enabled(reduce_motion=True, env={}) is False


def test_ci_disables() -> None:
    assert animations_enabled(env={"CI": "true"}) is False


def test_pytest_current_test_disables() -> None:
    assert animations_enabled(env={"PYTEST_CURRENT_TEST": "test_x"}) is False


def test_term_dumb_disables() -> None:
    assert animations_enabled(env={"TERM": "dumb"}) is False


def test_explicit_on_beats_ci() -> None:
    assert animations_enabled(env={"ECDAT_ANIM": "1", "CI": "true"}) is True


def test_explicit_off_beats_everything() -> None:
    assert animations_enabled(reduce_motion=True, env={"ECDAT_ANIM": "0"}) is False


# ---- clamp01 / ease_out_cubic ---------------------------------------------


@pytest.mark.parametrize(
    "value,expected", [(-1.0, 0.0), (0.0, 0.0), (0.5, 0.5), (1.0, 1.0), (2.0, 1.0)]
)
def test_clamp01(value: float, expected: float) -> None:
    assert clamp01(value) == expected


def test_ease_out_cubic_bounds_and_monotonic() -> None:
    assert ease_out_cubic(0.0) == 0.0
    assert ease_out_cubic(1.0) == 1.0
    values = [ease_out_cubic(i / 10) for i in range(11)]
    assert values == sorted(values)
    assert ease_out_cubic(0.5) > 0.5


# ---- count_up_value -------------------------------------------------------


@pytest.mark.parametrize("progress,expected", [(0.0, 0), (-0.5, 0), (1.0, 100), (2.0, 100)])
def test_count_up_value_bounds(progress: float, expected: int) -> None:
    assert count_up_value(100, progress) == expected


def test_count_up_value_midway_is_between() -> None:
    mid = count_up_value(100, 0.5)
    assert 50 < mid < 100


def test_count_up_value_monotonic() -> None:
    values = [count_up_value(50, i / 20) for i in range(21)]
    assert values == sorted(values)


# ---- scramble -------------------------------------------------------------


def test_scramble_complete_returns_final() -> None:
    assert scramble("ECDAT", 1.0, 99) == "ECDAT"
    assert scramble("ECDAT", 2.0, 99) == "ECDAT"


def test_scramble_preserves_length() -> None:
    result = scramble("HELLO WORLD", 0.0, 3)
    assert len(result) == len("HELLO WORLD")


def test_scramble_keeps_spaces() -> None:
    result = scramble("A B C D", 0.0, 1)
    assert [i for i, ch in enumerate(result) if ch == " "] == [1, 3, 5]


def test_scramble_is_deterministic() -> None:
    assert scramble("ECDAT", 0.3, 7) == scramble("ECDAT", 0.3, 7)


def test_scramble_frame_changes_glyphs() -> None:
    assert scramble("XXXXX", 0.0, 0) != scramble("XXXXX", 0.0, 1)


def test_scramble_reveals_left_to_right() -> None:
    half = scramble("ABCDEFGH", 0.5, 0)
    assert half[:4] == "ABCD"


def test_scramble_empty_string() -> None:
    assert scramble("", 0.0, 5) == ""


# ---- FrameBudget ----------------------------------------------------------


def test_frame_budget_starts_full_quality() -> None:
    budget = FrameBudget()
    assert budget.scale == 1.0
    assert budget.disabled is False
    assert budget.average_ms == 0.0


def test_frame_budget_scales_down_when_slow() -> None:
    budget = FrameBudget(target_ms=10.0, window=4)
    for _ in range(4):
        budget.record(0.02)  # 20 ms > target
    assert budget.scale > 1.0


def test_frame_budget_hysteresis_recovers() -> None:
    budget = FrameBudget(target_ms=10.0, window=4)
    for _ in range(4):
        budget.record(0.02)
    assert budget.scale > 1.0
    for _ in range(8):
        budget.record(0.001)  # 1 ms — well under target
    assert budget.scale == 1.0


def test_frame_budget_disables_when_very_slow() -> None:
    budget = FrameBudget(target_ms=10.0, window=4)
    for _ in range(4):
        budget.record(0.1)  # 100 ms > 4x target
    assert budget.disabled is True


def test_frame_budget_reset() -> None:
    budget = FrameBudget(target_ms=10.0, window=2)
    budget.record(1.0)
    budget.record(1.0)
    budget.reset()
    assert budget.disabled is False
    assert budget.scale == 1.0
    assert budget.average_ms == 0.0
