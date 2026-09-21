"""Tests for ``ecdat mosca`` and ``ecdat.ui.render.mosca_timeline`` (Phase 77).

Covers the pure segment builder (exact-width invariant, the exposed-window row
appearing iff ``X + Y > Z``, the minimum-one-cell rule, and the degenerate
``x = y = 0`` case) plus the command's exit codes and classification boundary.
"""

from __future__ import annotations

import pytest

from ecdat.cli.commands import mosca as mosca_cmd
from ecdat.cli.main import main
from ecdat.ui.render import mosca_timeline, mosca_timeline_segments
from ecdat_core.risk_engine import classify_urgency


class _MoscaArgs:
    def __init__(self, x=None, y=None, z=None) -> None:
        self.x = x
        self.y = y
        self.z = z


def _rows(x: float, y: float, z: float, width: int):
    rows = mosca_timeline_segments(x, y, z, width)
    texts = ["".join(text for text, _ in row) for row in rows]
    return rows, texts


# ---- pure segment function ------------------------------------------------


@pytest.mark.parametrize("width", [1, 2, 5, 6, 7, 20, 40, 64, 120, 200])
@pytest.mark.parametrize("x,y,z", [(10, 3, 8), (0, 0, 8), (5, 5, 8), (1, 1, 100)])
def test_every_row_is_exactly_width_cells(x, y, z, width) -> None:
    _, texts = _rows(x, y, z, width)
    assert texts, "expected at least one row"
    assert all(len(t) == width for t in texts)


def test_row3_present_only_when_violation() -> None:
    _, exposed = _rows(10, 3, 8, 64)
    assert len(exposed) == 4  # X + Y = 13 > 8

    _, safe = _rows(3, 3, 8, 64)
    assert len(safe) == 3  # X + Y = 6 < 8

    _, equal = _rows(5, 3, 8, 64)
    assert len(equal) == 3  # X + Y == Z is not a violation


def test_exposed_window_uses_gap_token() -> None:
    rows, _ = _rows(10, 3, 8, 64)
    tokens = [token for _, token in rows[2]]
    assert "gap" in tokens


def test_gap_row_absent_when_safe() -> None:
    rows, _ = _rows(1, 1, 10, 64)
    assert all("gap" not in {tok for _, tok in row} for row in rows)


def test_named_style_tokens_used() -> None:
    rows, _ = _rows(10, 3, 8, 64)
    assert {tok for _, tok in rows[0]} >= {"x", "y"}
    assert {tok for _, tok in rows[1]} >= {"z"}
    assert {tok for _, tok in rows[3]} >= {"label"}


def test_every_row_ends_with_fitted_width_and_labels() -> None:
    _, texts = _rows(10, 3, 8, 64)
    assert texts[0].startswith("NOW \u251c")
    assert texts[1].startswith("NOW \u251c")
    assert texts[3].startswith("X data lifetime")


def test_minimum_one_cell_for_tiny_nonzero_values() -> None:
    """A non-zero value must always be visible, however small the scale."""
    rows, _ = _rows(0.001, 0.001, 10000, 64)
    x_cells = [text for text, tok in rows[0] if tok == "x"]
    y_cells = [text for text, tok in rows[0] if tok == "y"]
    assert x_cells and len(x_cells[0]) >= 1
    assert y_cells and len(y_cells[0]) >= 1


def test_degenerate_zero_x_and_y() -> None:
    rows, texts = _rows(0, 0, 8, 64)
    assert len(texts) == 3  # no exposed window
    assert all(len(t) == 64 for t in texts)
    tokens = {tok for row in rows for _, tok in row}
    assert "x" not in tokens
    assert "y" not in tokens


def test_zero_z_with_positive_sum_shows_full_exposure() -> None:
    _, texts = _rows(5, 5, 0, 64)
    assert len(texts) == 4


def test_mosca_timeline_returns_renderable_group() -> None:
    from rich.console import Group

    group = mosca_timeline(10, 3, 8)
    assert isinstance(group, Group)


# ---- classification boundary ---------------------------------------------


def test_ratio_exactly_one_is_critical() -> None:
    assert classify_urgency(1.0) == "critical"


@pytest.mark.parametrize(
    "ratio,expected",
    [
        (1.0, "critical"),
        (0.99, "high"),
        (0.8, "high"),
        (0.79, "medium"),
        (0.5, "medium"),
        (0.49, "low"),
        (0.0, "low"),
    ],
)
def test_classify_urgency_thresholds(ratio: float, expected: str) -> None:
    assert classify_urgency(ratio) == expected


# ---- command --------------------------------------------------------------


def test_mosca_command_success(capsys: pytest.CaptureFixture[str]) -> None:
    rc = mosca_cmd.run(_MoscaArgs(x=10, y=3, z=8))
    out = capsys.readouterr().out
    assert rc == 0
    assert "exposed for 5 years" in out
    assert "CRITICAL" in out


def test_mosca_command_safety_margin(capsys: pytest.CaptureFixture[str]) -> None:
    rc = mosca_cmd.run(_MoscaArgs(x=1, y=1, z=10))
    out = capsys.readouterr().out
    assert rc == 0
    assert "safety margin" in out
    assert "LOW" in out


def test_mosca_command_boundary_is_critical(
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = mosca_cmd.run(_MoscaArgs(x=5, y=3, z=8))
    out = capsys.readouterr().out
    assert rc == 0
    assert "CRITICAL" in out
    assert "safety margin" in out


def test_mosca_command_draws_timeline(capsys: pytest.CaptureFixture[str]) -> None:
    rc = mosca_cmd.run(_MoscaArgs(x=10, y=3, z=8))
    out = capsys.readouterr().out
    assert rc == 0
    assert "NOW \u251c" in out
    assert "\u2592" in out  # exposed-window fill


def test_mosca_missing_args_non_interactive_exits_2(
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = mosca_cmd.run(_MoscaArgs(x=10, y=3, z=None))
    captured = capsys.readouterr()
    assert rc == 2
    assert "quantum arrival" in captured.err


def test_mosca_all_args_missing_non_interactive_exits_2(
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = mosca_cmd.run(_MoscaArgs())
    captured = capsys.readouterr()
    assert rc == 2
    assert "data lifetime" in captured.err


def test_mosca_rejects_negative_x(capsys: pytest.CaptureFixture[str]) -> None:
    rc = mosca_cmd.run(_MoscaArgs(x=-1, y=3, z=8))
    captured = capsys.readouterr()
    assert rc == 2
    assert ">= 0" in captured.err


def test_mosca_rejects_negative_y(capsys: pytest.CaptureFixture[str]) -> None:
    rc = mosca_cmd.run(_MoscaArgs(x=1, y=-3, z=8))
    assert rc == 2


def test_mosca_rejects_zero_z(capsys: pytest.CaptureFixture[str]) -> None:
    rc = mosca_cmd.run(_MoscaArgs(x=1, y=3, z=0))
    captured = capsys.readouterr()
    assert rc == 2
    assert "> 0" in captured.err


def test_mosca_rejects_negative_z(capsys: pytest.CaptureFixture[str]) -> None:
    rc = mosca_cmd.run(_MoscaArgs(x=1, y=3, z=-8))
    assert rc == 2


def test_mosca_zero_x_allowed(capsys: pytest.CaptureFixture[str]) -> None:
    rc = mosca_cmd.run(_MoscaArgs(x=0, y=0, z=8))
    assert rc == 0


# ---- dispatch + argparse integration --------------------------------------


def test_main_dispatches_mosca(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["mosca", "-x", "10", "-y", "3", "-z", "8"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "exposed for 5 years" in out


def test_main_accepts_long_aliases(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(
        [
            "mosca",
            "--shelf-life",
            "10",
            "--migration",
            "3",
            "--threat",
            "8",
        ]
    )
    assert rc == 0
    assert "CRITICAL" in capsys.readouterr().out


def test_main_mosca_missing_args_exits_2() -> None:
    rc = main(["mosca", "-x", "10", "-y", "3"])
    assert rc == 2
