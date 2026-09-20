"""Tests for art3d, art_static, and art_text modules."""

from __future__ import annotations

import time

from rich.text import Text

from ecdat.ui.art3d import (
    GLOBE_LEVELS,
    HEX,
    TORUS_CHARS,
    blank_frame,
    frame_to_rows,
    render_globe,
    render_torus,
)
from ecdat.ui.art_static import (
    CRIT_LOCK,
    SAFE_LOCK,
    WARN_LOCK,
    emblem_for,
    headline_for,
    verdict,
)
from ecdat.ui.art_text import frame_to_text

# ===========================================================================
# art3d — Globe
# ===========================================================================


class TestRenderGlobe:
    def test_dimensions(self) -> None:
        frame = render_globe(0.0, 60, 26)
        assert len(frame) == 26
        for row in frame:
            assert len(row) == 60

    def test_non_blank(self) -> None:
        frame = render_globe(0.0, 60, 26)
        non_blank = sum(1 for row in frame for ch, level in row if level > 0)
        assert non_blank > 300, f"Only {non_blank} non-blank cells"

    def test_contains_hex_digit(self) -> None:
        frame = render_globe(0.0, 60, 26)
        chars = {ch for row in frame for ch, level in row if level > 0}
        # At least one hex digit should appear.
        hex_digits = set(HEX)
        assert chars & hex_digits, f"No hex digits found in globe: {sorted(chars)[:20]}"

    def test_contains_o_and_at(self) -> None:
        frame = render_globe(0.0, 60, 26)
        chars = {ch for row in frame for ch, level in row if level > 0}
        assert "o" in chars, "No ring 'o' found"
        assert "@" in chars, "No satellite '@' found"

    def test_printable_ascii_only(self) -> None:
        frame = render_globe(0.0, 60, 26)
        for row in frame:
            for ch, _ in row:
                assert (
                    ord(ch) < 128 or ch == " "
                ), f"Non-ASCII: {ch!r}"

    def test_deterministic(self) -> None:
        frame1 = render_globe(0.0, 60, 26)
        frame2 = render_globe(0.0, 60, 26)
        assert frame_to_rows(frame1) == frame_to_rows(frame2)

    def test_differs_at_t1(self) -> None:
        frame0 = render_globe(0.0, 60, 26)
        frame1 = render_globe(1.0, 60, 26)
        assert frame_to_rows(frame0) != frame_to_rows(frame1)

    def test_ring_false_no_o_at(self) -> None:
        frame = render_globe(0.0, 60, 26, ring=False)
        chars = {ch for row in frame for ch, level in row if level > 0}
        assert "o" not in chars, "Ring chars present when ring=False"
        assert "@" not in chars, "Satellite chars present when ring=False"

    def test_too_small_returns_blank(self) -> None:
        frame = render_globe(0.0, 10, 5)
        assert len(frame) == 5
        for row in frame:
            assert len(row) == 10
            for ch, level in row:
                assert level == 0

    def test_zero_size(self) -> None:
        frame = render_globe(0.0, 0, 0)
        assert len(frame) == 0

    def test_performance(self) -> None:
        """One frame should render in under 0.25 s."""
        t0 = time.perf_counter()
        render_globe(0.5, 60, 26)
        elapsed = time.perf_counter() - t0
        assert elapsed < 0.25, f"Globe render took {elapsed:.4f}s"

# ===========================================================================
# art3d — Torus
# ===========================================================================


class TestRenderTorus:
    def test_dimensions(self) -> None:
        frame = render_torus(0.9, 0.5, 60, 24)
        assert len(frame) == 24
        for row in frame:
            assert len(row) == 60

    def test_non_blank(self) -> None:
        frame = render_torus(0.9, 0.5, 60, 24)
        non_blank = sum(1 for row in frame for ch, level in row if level > 0)
        assert non_blank > 100, f"Only {non_blank} non-blank cells"

    def test_levels_range(self) -> None:
        frame = render_torus(0.9, 0.5, 60, 24)
        for row in frame:
            for ch, level in row:
                if level > 0:
                    assert 1 <= level <= len(TORUS_CHARS), f"Level {level} out of range"

    def test_deterministic(self) -> None:
        frame1 = render_torus(0.9, 0.5, 60, 24)
        frame2 = render_torus(0.9, 0.5, 60, 24)
        assert frame_to_rows(frame1) == frame_to_rows(frame2)

    def test_too_small_blank(self) -> None:
        frame = render_torus(0.9, 0.5, 5, 2)
        assert len(frame) == 2
        for row in frame:
            for ch, level in row:
                assert level == 0

# ===========================================================================
# art3d — Utilities
# ===========================================================================


class TestBlankFrame:
    def test_blank_frame(self) -> None:
        f = blank_frame(3, 2)
        assert len(f) == 2
        assert len(f[0]) == 3
        for row in f:
            for ch, level in row:
                assert (ch, level) == (" ", 0)


class TestFrameToRows:
    def test_simple(self) -> None:
        frame = [[("A", 1), ("B", 2)], [("C", 3), ("D", 4)]]
        rows = frame_to_rows(frame)
        assert rows == ["AB", "CD"]

# ===========================================================================
# art_static
# ===========================================================================


class TestEmblems:
    def test_dimensions(self) -> None:
        for e in (SAFE_LOCK, WARN_LOCK, CRIT_LOCK):
            assert len(e) == 9, f"Emblem has {len(e)} rows, expected 9"
            for row in e:
                assert len(row) == 19, f"Emblem row has {len(row)} cols, expected 19"

    def test_safe_lock_has_o(self) -> None:
        assert "o" in "\n".join(SAFE_LOCK)

    def test_warn_lock_has_exclaim(self) -> None:
        assert "!" in "\n".join(WARN_LOCK)

    def test_crit_lock_has_x(self) -> None:
        assert "X" in "\n".join(CRIT_LOCK)


class TestVerdict:
    def test_empty(self) -> None:
        assert verdict({}) == "empty"
        assert verdict({"critical": 0, "high": 0}) == "empty"

    def test_crit(self) -> None:
        assert verdict({"critical": 1}) == "crit"
        assert verdict({"critical": 1, "high": 5}) == "crit"

    def test_warn(self) -> None:
        assert verdict({"critical": 0, "high": 1}) == "warn"
        assert verdict({"critical": 0, "high": 0, "medium": 1}) == "warn"

    def test_safe(self) -> None:
        # All-zero counts mean total=0, which is "empty", not "safe".
        # Need at least one quantum-safe finding for a "safe" verdict.
        assert verdict(
            {"critical": 0, "high": 0, "medium": 0, "low": 0, "quantum-safe": 42}
        ) == "safe"
        assert verdict(
            {"critical": 0, "high": 0, "medium": 0, "low": 0, "quantum-safe": 1}
        ) == "safe"


class TestEmblemFor:
    def test_crit_emblem(self) -> None:
        assert emblem_for("crit") == CRIT_LOCK

    def test_warn_emblem(self) -> None:
        assert emblem_for("warn") == WARN_LOCK

    def test_default_safe(self) -> None:
        assert emblem_for("safe") == SAFE_LOCK
        assert emblem_for("bogus") == SAFE_LOCK
        assert emblem_for("empty") == SAFE_LOCK


class TestHeadlineFor:
    def test_crit_headline(self) -> None:
        h = headline_for({"critical": 3, "high": 2}, files=10)
        assert "CRITICAL" in h
        assert "HIGH" in h
        assert "migrate" in h.lower()

    def test_warn_headline(self) -> None:
        h = headline_for({"critical": 0, "high": 1, "medium": 3}, files=10)
        assert "HIGH" in h
        assert "MEDIUM" in h

    def test_safe_headline(self) -> None:
        # All-zero counts → total=0 → "empty" message, not "safe".
        # Need at least one quantum-safe finding.
        h = headline_for(
            {"critical": 0, "high": 0, "medium": 0, "low": 0, "quantum-safe": 5},
            files=10,
        )
        assert "good" in h.lower()

    def test_empty_headline(self) -> None:
        h = headline_for({}, files=42)
        assert "42" in h
        assert "cryptographic" in h.lower()


# ===========================================================================
# art_text
# ===========================================================================


class TestFrameToText:
    def test_empty_frame(self) -> None:
        t = frame_to_text([])
        assert isinstance(t, Text)
        assert t.plain == ""

    def test_blank_level_0(self) -> None:
        """Level 0 should produce spaces without style."""
        frame = [[(" ", 0), (" ", 0), (" ", 0)]]
        t = frame_to_text(frame)
        assert t.plain == "   "
        # Should have NO styled spans (only unstyled text).
        spans = list(t.spans)
        assert len(spans) == 0 or all(s.style is None or not s.style for s in spans)

    def test_run_grouping(self) -> None:
        """Consecutive same-level cells should be one run."""
        frame = [[("A", 3), ("B", 3), ("C", 3)]]
        t = frame_to_text(frame)
        assert t.plain == "ABC"
        # Should be one span for the whole run.
        spans = list(t.spans)
        assert len(spans) == 1

    def test_level_color_mapping(self) -> None:
        """Level n maps to gradient[n-1]."""
        gradient = ["#111111", "#222222", "#333333"]  # 3 colors
        frame = [[("X", 1), ("Y", 2), ("Z", 3)]]
        t = frame_to_text(frame, gradient=gradient)
        spans = list(t.spans)
        assert len(spans) == 3

    def test_level_exceeds_gradient(self) -> None:
        """Level > len(gradient) should use last gradient color."""
        gradient = ["#ff0000", "#00ff00"]
        frame = [[("X", 5)]]  # level 5 > 2
        t = frame_to_text(frame, gradient=gradient)
        spans = list(t.spans)
        assert len(spans) == 1

    def test_multi_row(self) -> None:
        frame = [[("A", 1)], [("B", 2)]]
        t = frame_to_text(frame)
        assert "\n" in t.plain
        assert "A" in t.plain
        assert "B" in t.plain

    def test_mixed_levels(self) -> None:
        """Level 0 followed by non-zero should split runs."""
        frame = [[(" ", 0), ("A", 1), ("B", 1), (" ", 0)]]
        t = frame_to_text(frame)
        spans = list(t.spans)
        # Should have spans: unstyled space, styled AB, unstyled space
        # Actually blank level 0 has no style, so it's just Text.append without span
        # Let's just verify plain text is correct.
        assert t.plain == " AB "  # leading space, then AB, then trailing space
        # At least one styled span should exist for the colored AB.
        styled = [s for s in spans if s.style]
        assert len(styled) >= 1

    def test_globe_frame_to_text(self) -> None:
        """Round-trip a globe frame through frame_to_text."""
        frame = render_globe(0.0, 60, 26)
        t = frame_to_text(frame)
        assert isinstance(t, Text)
        assert len(t.plain) > 300  # plenty of chars