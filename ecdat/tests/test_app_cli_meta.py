"""Tests for the meta commands: ``help``, ``version``, ``doctor``, ``about``."""

from __future__ import annotations

from ecdat.cli import main
from ecdat.cli.parser import COMMANDS


# ---------------------------------------------------------------------------
# help
# ---------------------------------------------------------------------------


class TestHelp:
    def test_help_lists_every_registered_command(self, capsys):
        rc = main(["help"])
        out = capsys.readouterr().out
        assert rc == 0
        for name in COMMANDS:
            assert name in out

    def test_help_overview_shows_quick_start_and_exit_codes(self, capsys):
        rc = main(["help"])
        out = capsys.readouterr().out
        assert rc == 0
        assert "Quick start" in out
        assert "Exit codes" in out
        assert "130" in out

    def test_help_for_a_command_renders_its_usage(self, capsys):
        rc = main(["help", "scan"])
        out = capsys.readouterr().out
        assert rc == 0
        assert "usage" in out.lower()
        assert "--fail-on" in out

    def test_help_unknown_command_exits_2(self, capsys):
        rc = main(["help", "nope"])
        captured = capsys.readouterr()
        assert rc == 2
        assert captured.out == ""
        assert "nope" in captured.err
        for name in COMMANDS:
            assert name in captured.err

    def test_short_help_flag_still_works(self, capsys):
        rc = main(["-h"])
        out = capsys.readouterr().out
        assert rc == 0
        assert "usage" in out.lower()


# ---------------------------------------------------------------------------
# version
# ---------------------------------------------------------------------------


class TestVersion:
    def test_version_command_line(self, capsys):
        rc = main(["version"])
        out = capsys.readouterr().out
        assert rc == 0
        assert out.startswith("ecdat ")
        assert "engine ecdat_core" in out
        assert "signatures" in out
        assert "Python" in out

    def test_version_flag_matches_command(self, capsys):
        rc_flag = main(["--version"])
        out_flag = capsys.readouterr().out
        rc_cmd = main(["version"])
        out_cmd = capsys.readouterr().out
        assert rc_flag == 0 and rc_cmd == 0
        assert out_flag == out_cmd


# ---------------------------------------------------------------------------
# doctor
# ---------------------------------------------------------------------------


class TestDoctor:
    def test_doctor_exits_zero_in_test_env(self, capsys):
        rc = main(["doctor"])
        out = capsys.readouterr().out
        assert rc == 0
        assert "Python" in out
        assert "signatures" in out

    def test_doctor_reports_home_is_writable(self, capsys):
        rc = main(["doctor"])
        out = capsys.readouterr().out
        assert rc == 0
        assert "ECDAT_HOME" in out
        assert "writable" in out


# ---------------------------------------------------------------------------
# about
# ---------------------------------------------------------------------------


class TestAbout:
    def test_about_spin_zero_non_tty_has_no_escapes(self, capsys):
        rc = main(["about", "--spin", "0"])
        captured = capsys.readouterr()
        assert rc == 0
        assert "\x1b" not in captured.out
        assert "MIT" in captured.out
        assert "Built with Rich" in captured.out

    def test_about_never_animates_when_not_a_tty(self, monkeypatch, capsys):
        import ecdat.ui.motion as motion

        monkeypatch.setattr(motion, "animations_enabled", lambda *a, **k: True)

        rc = main(["about", "--spin", "1"])
        captured = capsys.readouterr()
        assert rc == 0
        assert "\x1b" not in captured.out

    def test_about_no_anim_is_static(self, capsys):
        rc = main(["about", "--no-anim"])
        captured = capsys.readouterr()
        assert rc == 0
        assert "\x1b" not in captured.out
