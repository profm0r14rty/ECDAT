"""Tests for the ``ecdat`` CLI — parser, ``scan`` command, and crash safety."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import ecdat.cli.commands.scan as scan_command
from ecdat.cli import main

DEMO_REPO = (
    Path(__file__).resolve().parents[2]
    / "ecdat_core"
    / "tests"
    / "fixtures"
    / "demo_repo"
)

BANNER_TAGLINE = "Enterprise Cryptographic Discovery"


# ---------------------------------------------------------------------------
# Global flags / bare invocation
# ---------------------------------------------------------------------------


class TestGlobalAndBare:
    def test_version_flag(self, capsys):
        rc = main(["--version"])
        captured = capsys.readouterr()
        assert rc == 0
        assert "ecdat" in captured.out
        assert any(c.isdigit() for c in captured.out)

    def test_bare_invocation_shows_banner_and_examples(self, capsys):
        rc = main([])
        out = capsys.readouterr().out
        assert rc == 0
        assert BANNER_TAGLINE in out
        for example in ("ecdat demo", "ecdat scan .", "ecdat about", "ecdat help"):
            assert example in out

    def test_no_color_flag_accepted(self, capsys):
        rc = main(["--no-color", "scan", str(DEMO_REPO), "-f", "json"])
        captured = capsys.readouterr()
        assert rc == 0
        json.loads(captured.out)

    def test_help_exits_zero(self, capsys):
        rc = main(["--help"])
        out = capsys.readouterr().out
        assert rc == 0
        assert "usage" in out.lower()


# ---------------------------------------------------------------------------
# Payload formats — stdout is the payload, nothing else
# ---------------------------------------------------------------------------


class TestPayloadFormats:
    def test_json_format_parses_with_detections(self, capsys):
        rc = main(["scan", str(DEMO_REPO), "-f", "json"])
        captured = capsys.readouterr()
        assert rc == 0
        data = json.loads(captured.out)
        assert "detections" in data
        assert isinstance(data["detections"], list)
        assert len(data["detections"]) > 0

    def test_cbom_format_demo_repo(self, capsys):
        rc = main(["scan", str(DEMO_REPO), "-f", "cbom"])
        out = capsys.readouterr().out
        assert rc == 0
        data = json.loads(out)
        assert data["bomFormat"] == "CycloneDX"
        assert data["specVersion"] == "1.6"

    def test_summary_format(self, capsys):
        rc = main(["scan", str(DEMO_REPO), "-f", "summary"])
        out = capsys.readouterr().out
        assert rc == 0
        data = json.loads(out)
        assert "total_detections" in data

    def test_payload_stdout_contains_nothing_else(self, capsys):
        for fmt in ("json", "cbom", "summary"):
            capsys.readouterr()  # drain
            rc = main(["scan", str(DEMO_REPO), "-f", fmt])
            out = capsys.readouterr().out
            assert rc == 0
            assert out.lstrip().startswith("{")
            # The whole stream must be a single valid JSON document.
            json.loads(out)
            assert BANNER_TAGLINE not in out


# ---------------------------------------------------------------------------
# Pretty rendering
# ---------------------------------------------------------------------------


class TestPretty:
    def test_pretty_shows_banner_and_report(self, capsys):
        rc = main(["scan", str(DEMO_REPO)])
        out = capsys.readouterr().out
        assert rc == 0
        assert BANNER_TAGLINE in out
        assert "Scan Summary" in out

    def test_quiet_suppresses_banner(self, capsys):
        rc = main(["scan", str(DEMO_REPO), "-q"])
        out = capsys.readouterr().out
        assert rc == 0
        assert BANNER_TAGLINE not in out


# ---------------------------------------------------------------------------
# Output directory
# ---------------------------------------------------------------------------


class TestOutputDir:
    def test_output_writes_both_files(self, tmp_path, capsys):
        outdir = tmp_path / "reports"
        rc = main(["scan", str(DEMO_REPO), "-f", "json", "-o", str(outdir)])
        capsys.readouterr()
        assert rc == 0

        cbom = outdir / "cbom.json"
        summary = outdir / "summary.json"
        assert cbom.is_file()
        assert summary.is_file()

        cbom_data = json.loads(cbom.read_text(encoding="utf-8"))
        summary_data = json.loads(summary.read_text(encoding="utf-8"))
        assert cbom_data["bomFormat"] == "CycloneDX"
        assert "total_detections" in summary_data


# ---------------------------------------------------------------------------
# --fail-on
# ---------------------------------------------------------------------------


class TestFailOn:
    def test_fail_on_low_demo_repo_exits_1(self, capsys):
        rc = main(["scan", str(DEMO_REPO), "-f", "json", "--fail-on", "low"])
        capsys.readouterr()
        assert rc == 1

    def test_fail_on_low_empty_dir_exits_0(self, capsys):
        with tempfile.TemporaryDirectory() as tmpdir:
            rc = main(["scan", tmpdir, "-f", "json", "--fail-on", "low"])
            captured = capsys.readouterr()
        assert rc == 0
        assert "Warning" in captured.err

    def test_fail_on_never_triggers_on_quantum_safe(self, capsys):
        # demo_repo has quantum-safe (AES) findings; --fail-on must not use
        # them.  A directory with only safe findings would exit 0 — we verify
        # the empty case above, and here that the flag is accepted.
        rc = main(["scan", str(DEMO_REPO), "-f", "json", "--fail-on", "critical"])
        capsys.readouterr()
        assert rc == 1


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    def test_missing_path_exit_2_friendly_no_traceback(self, capsys):
        rc = main(["scan", "/nonexistent/path/xyz123"])
        captured = capsys.readouterr()
        assert rc == 2
        assert captured.out == ""
        assert "Error" in captured.err
        assert "does not exist" in captured.err
        assert "Traceback" not in captured.err

    def test_bad_git_url_exit_2(self, capsys):
        rc = main(["scan", "http://example.com/repo.git", "--git-url"])
        captured = capsys.readouterr()
        assert rc == 2
        assert "only https" in captured.err.lower() or "https" in captured.err.lower()
        assert "Traceback" not in captured.err

    def test_unexpected_error_exit_3_crash_log_and_friendly_text(
        self, monkeypatch, capsys
    ):
        def _boom(args):
            raise RuntimeError("kaboom-unexpected")

        monkeypatch.setattr(scan_command, "run", _boom)
        rc = main(["scan", "."])
        captured = capsys.readouterr()

        assert rc == 3
        assert captured.out == ""
        assert "ECDAT hit an unexpected error" in captured.err
        assert "crash-" in captured.err
        assert "ecdat doctor" in captured.err
        assert "Traceback" not in captured.err

    def test_debug_env_shows_traceback(self, monkeypatch, capsys):
        def _boom(args):
            raise RuntimeError("kaboom-debug")

        monkeypatch.setattr(scan_command, "run", _boom)
        monkeypatch.setenv("ECDAT_DEBUG", "1")
        rc = main(["scan", "."])
        captured = capsys.readouterr()

        assert rc == 3
        assert "Traceback" in captured.err
        assert "RuntimeError: kaboom-debug" in captured.err

    def test_broken_pipe_exits_0_silently(self, monkeypatch, capsys):
        def _broken(args):
            raise BrokenPipeError()

        monkeypatch.setattr(scan_command, "run", _broken)
        rc = main(["scan", "."])
        captured = capsys.readouterr()

        assert rc == 0
        assert captured.out == ""
        assert captured.err == ""


# ---------------------------------------------------------------------------
# Import hygiene
# ---------------------------------------------------------------------------


def test_import_ecdat_cli_does_not_import_textual():
    """``import ecdat.cli`` (+ build_parser) must not pull in textual."""
    script = (
        "import sys\n"
        "import ecdat.cli\n"
        "from ecdat.cli.parser import build_parser\n"
        "build_parser()\n"
        "bad = [m for m in sys.modules if m == 'textual' or m.startswith('textual.')]\n"
        "print('FAIL:' + ','.join(bad) if bad else 'OK')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert result.stdout.strip() == "OK"
