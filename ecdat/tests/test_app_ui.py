"""Tests for theme, console, motion, and banner modules."""

from __future__ import annotations

import io
import os

import pytest
from rich.text import Text

from ecdat.ui.banner import (
    BANNER_ASCII_LINES,
    BANNER_LINES,
    SUBLINE,
    TAGLINE,
    banner_text,
    render_banner,
)
from ecdat.ui.console import _ensure_utf8_streams, is_interactive, make_console
from ecdat.ui.motion import animations_enabled
from ecdat.ui.theme import (
    MINT_GRADIENT,
    hex_to_rgb,
    lerp_hex,
    gradient,
    rich_theme,
    rgb_to_hex,
)

# ===========================================================================
# theme.py
# ===========================================================================


class TestGradientEndpoints:
    """gradient() must always start and end at the exact stop values."""

    def test_two_stops(self) -> None:
        result = gradient(["#000000", "#ffffff"], 5)
        assert len(result) == 5
        assert result[0] == "#000000"
        assert result[-1] == "#ffffff"
        # Interior should be grey.
        assert result[2] != "#000000"
        assert result[2] != "#ffffff"

    def test_three_stops(self) -> None:
        result = gradient(["#000000", "#888888", "#ffffff"], 7)
        assert len(result) == 7
        assert result[0] == "#000000"
        assert result[-1] == "#ffffff"

    def test_steps_1(self) -> None:
        result = gradient(["#ff0000", "#0000ff"], 1)
        assert result == ["#ff0000"]

    def test_steps_0(self) -> None:
        assert gradient(["#ff0000", "#0000ff"], 0) == []

    def test_single_stop(self) -> None:
        result = gradient(["#abcdef"], 5)
        assert result == ["#abcdef"] * 5

    def test_mint_gradient_length(self) -> None:
        assert len(MINT_GRADIENT) == 12
        assert MINT_GRADIENT[0] != MINT_GRADIENT[-1]


class TestHexRgb:
    def test_hex_to_rgb(self) -> None:
        assert hex_to_rgb("#ff0000") == (255, 0, 0)
        assert hex_to_rgb("#00ff00") == (0, 255, 0)
        assert hex_to_rgb("ffffff") == (255, 255, 255)
        assert hex_to_rgb("#000000") == (0, 0, 0)

    def test_rgb_to_hex(self) -> None:
        assert rgb_to_hex(255, 0, 0) == "#ff0000"
        assert rgb_to_hex(0, 0, 0) == "#000000"
        assert rgb_to_hex(0, 128, 255) == "#0080ff"

    def test_lerp_hex_midpoint(self) -> None:
        assert lerp_hex("#000000", "#ffffff", 0.5) == "#808080"

    def test_lerp_hex_clamp(self) -> None:
        assert lerp_hex("#000000", "#ffffff", 2.0) == "#ffffff"
        assert lerp_hex("#000000", "#ffffff", -1.0) == "#000000"


class TestRichTheme:
    def test_rich_theme_styles(self) -> None:
        theme = rich_theme()
        styles = theme.styles
        assert "ecdat.accent" in styles
        assert "ecdat.critical" in styles
        assert "ecdat.high" in styles

# ===========================================================================
# console.py
# ===========================================================================


class TestNoColor:
    def test_no_color_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("NO_COLOR", "1")
        c = make_console()
        assert c.no_color is True

    def test_force_color_0(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FORCE_COLOR", "0")
        c = make_console()
        assert c.no_color is True

    def test_explicit_no_color_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("NO_COLOR", "1")
        c = make_console(no_color=False)
        assert c.no_color is False

    def test_explicit_no_color_true(self) -> None:
        c = make_console(no_color=True)
        assert c.no_color is True

    def test_stderr_console(self) -> None:
        c = make_console(stderr=True, no_color=True)
        assert c.file is not None


class TestEnsureUtf8Streams:
    def test_fake_non_utf8_stream(self) -> None:
        """_ensure_utf8_streams should never raise even with weird streams."""

        class FakeStream:
            encoding = "cp1252"

            def reconfigure(self, **kwargs):  # type: ignore[no-untyped-def]
                # Accept the call — simulate success.
                self.encoding = "utf-8"

        fake = FakeStream()

        # Temporarily patch sys.stdout to be the fake stream.
        import sys as _sys

        saved = _sys.stdout
        try:
            _sys.stdout = fake  # type: ignore[assignment]
            _ensure_utf8_streams()
            assert fake.encoding == "utf-8"
        finally:
            _sys.stdout = saved

    def test_not_reconfigure_utf8(self) -> None:
        """Should not reconfigure streams already in UTF-8."""

        class FakeUtf8:
            encoding = "UTF-8"
            reconfigured = False

            def reconfigure(self, **kwargs):  # type: ignore[no-untyped-def]
                self.reconfigured = True

        fake = FakeUtf8()
        import sys as _sys

        saved = _sys.stdout
        try:
            _sys.stdout = fake  # type: ignore[assignment]
            _ensure_utf8_streams()
            assert not fake.reconfigured
        finally:
            _sys.stdout = saved

    def test_no_reconfigure_method(self) -> None:
        """Stream without .reconfigure should not raise."""

        class NoReconf:
            encoding = "latin-1"

        fake = NoReconf()
        import sys as _sys

        saved = _sys.stdout
        try:
            _sys.stdout = fake  # type: ignore[assignment]
            _ensure_utf8_streams()  # should not raise
        finally:
            _sys.stdout = saved


class TestInteractive:
    def test_is_interactive(self) -> None:
        """is_interactive should just not raise."""
        assert isinstance(is_interactive(), bool)


# ===========================================================================
# motion.py
# ===========================================================================


class TestAnimationsEnabled:
    def test_default_on(self) -> None:
        """With no overriding env, animations should be on."""
        assert animations_enabled(env={}) is True

    def test_ecdat_anim_off_variants(self) -> None:
        for val in ("0", "off", "false", "no"):
            assert animations_enabled(env={"ECDAT_ANIM": val}) is False
        for val in ("0", "OFF", "False", "NO"):  # lower called inside
            assert animations_enabled(env={"ECDAT_ANIM": val}) is False

    def test_ecdat_anim_on_variants(self) -> None:
        for val in ("1", "on", "true", "yes"):
            assert animations_enabled(env={"ECDAT_ANIM": val}) is True

    def test_reduce_motion(self) -> None:
        assert animations_enabled(reduce_motion=True, env={}) is False

    def test_ci_disables(self) -> None:
        assert animations_enabled(env={"CI": "true"}) is False

    def test_pytest_disables(self) -> None:
        assert animations_enabled(env={"PYTEST_CURRENT_TEST": "test_x"}) is False

    def test_term_dumb_disables(self) -> None:
        assert animations_enabled(env={"TERM": "dumb"}) is False

    def test_explicit_on_overrides_ci(self) -> None:
        assert animations_enabled(
            env={"ECDAT_ANIM": "1", "CI": "true"}
        ) is True

    def test_explicit_off_overrides_all(self) -> None:
        assert animations_enabled(env={"ECDAT_ANIM": "0"}) is False

# ===========================================================================
# banner.py
# ===========================================================================


class TestBannerWidth:
    def test_unicode_banner_max_width(self) -> None:
        w = max(len(line) for line in BANNER_LINES)
        assert w <= 80, f"Banner too wide: {w}"

    def test_ascii_banner_pure_ascii(self) -> None:
        for line in BANNER_ASCII_LINES:
            for ch in line:
                assert ord(ch) < 128, f"Non-ASCII in ASCII banner: {ch!r}"

    def test_ascii_banner_max_width(self) -> None:
        w = max(len(line) for line in BANNER_ASCII_LINES)
        assert w <= 80, f"ASCII banner too wide: {w}"


class TestBannerText:
    def test_unicode_banner_plain(self) -> None:
        t = banner_text(unicode=True)
        assert isinstance(t, Text)
        # Should have gradient-styled spans.
        assert len(list(t.spans)) > 0

    def test_ascii_banner_plain(self) -> None:
        t = banner_text(unicode=False)
        plain = t.plain
        assert all(ord(c) < 128 for c in plain if c not in ("\n", " "))

    def test_shimmer_keeps_plain_text(self) -> None:
        """Shimmer should only change styling, not plain text."""
        t0 = banner_text(unicode=True, shimmer=None)
        t1 = banner_text(unicode=True, shimmer=0.5)
        assert t0.plain == t1.plain

    def test_shimmer_clamped(self) -> None:
        """Shimmer outside [0,1] should not crash."""
        t = banner_text(unicode=True, shimmer=2.5)
        assert t.plain


class TestRenderBanner:
    def test_with_version(self) -> None:
        group = render_banner("0.2.0")
        assert group is not None

    def test_ascii_render(self) -> None:
        group = render_banner("1.0.0", unicode=False)
        assert group is not None

    def test_banner_renders_to_console(self) -> None:
        """Render the full banner to a no-color console — should not raise."""
        c = make_console(no_color=True, width=100)
        with io.StringIO() as buf:
            c.file = buf  # type: ignore[assignment]
            c.print(render_banner("0.2.0"))

    def test_tagline_subline_present(self) -> None:
        assert "Enterprise" in TAGLINE
        assert "Cryptographic" in TAGLINE
        assert "CBOM" in SUBLINE