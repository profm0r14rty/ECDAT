"""App-layer end-to-end tests driving ``python -m ecdat`` as a subprocess.

Every test invokes the real CLI entry point, capturing exit codes, stdout,
and stderr.  Assertions are tight: exact exit codes, content checks, and
mandatory ``"Traceback" not in result.stderr`` on every case.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

DEMO_REPO = (
    Path(__file__).resolve().parents[2]
    / "ecdat_core"
    / "tests"
    / "fixtures"
    / "demo_repo"
)

BANNER_TAGLINE = "Enterprise Cryptographic Discovery"


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------


class Harness:
    """Subprocess harness that runs ``python -m ecdat`` in an isolated
    work directory with a dedicated ``ECDAT_HOME``.
    """

    __slots__ = ("cwd", "home", "env")

    def __init__(self, tmp_path: Path) -> None:
        self.cwd = tmp_path / "cwd"
        self.cwd.mkdir(parents=True, exist_ok=True)
        self.home = tmp_path / "home"
        self.home.mkdir(parents=True, exist_ok=True)
        self.env = {
            **os.environ,
            "ECDAT_HOME": str(self.home),
            "NO_COLOR": "1",
            "ECDAT_ANIM": "0",
        }

    def run(
        self,
        *args: str,
        env_overrides: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Invoke ``python -m ecdat`` with *args* in the harness cwd.

        Args:
            *args: CLI positional arguments (as strings).
            env_overrides: Extra env vars to merge on top of ``self.env``.

        Returns:
            A :class:`subprocess.CompletedProcess` with captured text output.
        """
        env = dict(self.env)
        if env_overrides:
            env.update(env_overrides)
        cmd = [sys.executable, "-m", "ecdat", *args]
        return subprocess.run(
            cmd,
            cwd=str(self.cwd),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=120,
        )


@pytest.fixture
def run(tmp_path: Path) -> Harness:
    """Return a :class:`Harness` rooted under *tmp_path*."""
    return Harness(tmp_path)


# ---------------------------------------------------------------------------
# Meta commands
# ---------------------------------------------------------------------------


class TestVersion:
    def test_version_flag_exits_zero_and_contains_ecdat(self, run: Harness):
        result = run.run("--version")
        assert result.returncode == 0
        assert "ecdat" in result.stdout
        assert result.stdout.strip() != ""
        assert "Traceback" not in result.stderr


class TestBare:
    def test_bare_no_args_exits_zero_and_shows_ecdat_help(self, run: Harness):
        result = run.run()
        assert result.returncode == 0
        assert "ecdat help" in result.stdout
        assert "Traceback" not in result.stderr


class TestHelp:
    def test_help_exits_zero_and_has_output(self, run: Harness):
        result = run.run("help")
        assert result.returncode == 0
        assert result.stdout.strip() != ""
        assert "Traceback" not in result.stderr

    def test_help_scan_shows_usage(self, run: Harness):
        result = run.run("help", "scan")
        assert result.returncode == 0
        assert "usage" in result.stdout.lower()
        assert "Traceback" not in result.stderr

    def test_help_nope_exits_2_and_stderr_nonempty(self, run: Harness):
        result = run.run("help", "nope")
        assert result.returncode == 2
        assert result.stdout == ""
        assert result.stderr.strip() != ""
        assert "Traceback" not in result.stderr


class TestDoctor:
    def test_doctor_exits_zero_and_has_output(self, run: Harness):
        result = run.run("doctor")
        assert result.returncode == 0
        assert result.stdout.strip() != ""
        assert "Traceback" not in result.stderr


# ---------------------------------------------------------------------------
# demo command
# ---------------------------------------------------------------------------


class TestDemo:
    def test_demo_json_exits_zero_pure_json_no_banner(self, run: Harness):
        result = run.run("demo", "-f", "json")
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert isinstance(data, dict)
        assert BANNER_TAGLINE not in result.stdout
        assert "Traceback" not in result.stderr


# ---------------------------------------------------------------------------
# scan command — successful paths
# ---------------------------------------------------------------------------


class TestScanSuccess:
    def test_cbom_format_exits_zero_valid_cyclonedx(self, run: Harness):
        result = run.run("scan", str(DEMO_REPO), "-f", "cbom")
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["bomFormat"] == "CycloneDX"
        assert data["specVersion"] == "1.6"
        assert "Traceback" not in result.stderr

    def test_summary_format_exits_zero_with_total_detections(self, run: Harness):
        result = run.run("scan", str(DEMO_REPO), "-f", "summary")
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert "total_detections" in data
        assert "Traceback" not in result.stderr

    def test_fail_on_low_demo_repo_exits_1_valid_json(self, run: Harness):
        result = run.run(
            "scan", str(DEMO_REPO), "-f", "json", "--fail-on", "low"
        )
        assert result.returncode == 1
        data = json.loads(result.stdout)
        assert isinstance(data, dict)
        assert len(data.get("detections", [])) > 0
        assert "Traceback" not in result.stderr

    def test_empty_directory_exits_zero_valid_json(self, run: Harness):
        empty = run.cwd / "empty"
        empty.mkdir(parents=True, exist_ok=True)
        result = run.run("scan", str(empty), "-f", "json")
        assert result.returncode == 0
        json.loads(result.stdout)  # must parse
        assert "Traceback" not in result.stderr

    def test_output_dir_writes_cbom_and_summary(self, run: Harness):
        outdir = run.cwd / "out"
        result = run.run(
            "scan", str(DEMO_REPO), "-f", "json", "-o", str(outdir)
        )
        assert result.returncode == 0

        cbom = outdir / "cbom.json"
        summary = outdir / "summary.json"
        assert cbom.is_file(), f"expected {cbom} to exist"
        assert summary.is_file(), f"expected {summary} to exist"

        cbom_data = json.loads(cbom.read_text(encoding="utf-8"))
        summary_data = json.loads(summary.read_text(encoding="utf-8"))
        assert cbom_data["bomFormat"] == "CycloneDX"
        assert "total_detections" in summary_data

        assert "Traceback" not in result.stderr


# ---------------------------------------------------------------------------
# scan command — error paths
# ---------------------------------------------------------------------------


class TestScanErrors:
    def test_missing_path_exits_2_no_stdout_friendly_error(self, run: Harness):
        result = run.run("scan", "/nonexistent/path/xyz123", "-f", "json")
        assert result.returncode == 2
        assert result.stdout == ""
        assert "Error" in result.stderr or "does not exist" in result.stderr
        assert "Traceback" not in result.stderr

    def test_http_git_url_exits_2_mentions_https(self, run: Harness):
        result = run.run("scan", "http://example.com/x.git", "-f", "json")
        assert result.returncode == 2
        assert "https" in result.stderr.lower()
        assert "Traceback" not in result.stderr

    def test_ssh_git_url_exits_2(self, run: Harness):
        result = run.run("scan", "ssh://git@example.com/x.git", "-f", "json")
        assert result.returncode == 2
        assert "Traceback" not in result.stderr


# ---------------------------------------------------------------------------
# about command
# ---------------------------------------------------------------------------


class TestAbout:
    def test_about_spin_zero_exits_zero_has_output(self, run: Harness):
        result = run.run("about", "--spin", "0")
        assert result.returncode == 0
        assert result.stdout.strip() != ""
        assert "Traceback" not in result.stderr


# ---------------------------------------------------------------------------
# Closed pipe
# ---------------------------------------------------------------------------


class TestClosedPipe:
    def test_closed_pipe_no_traceback(self, run: Harness):
        """Close stdout's read-end while a scan writes JSON — no traceback.

        On Python 3.14 the process may exit 120 and stderr may contain
        ``BrokenPipeError`` while flushing — this is expected.  We only
        assert ``b"Traceback" not in stderr``.
        """
        proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "ecdat",
                "scan",
                str(DEMO_REPO),
                "-f",
                "json",
            ],
            cwd=str(run.cwd),
            env=dict(run.env),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        # Give the scan a moment to start writing, then slam the pipe shut.
        proc.stdout.close()  # type: ignore[union-attr]
        stderr_bytes = proc.stderr.read()  # type: ignore[union-attr]
        proc.stderr.close()  # type: ignore[union-attr]
        proc.wait(timeout=120)

        assert b"Traceback" not in stderr_bytes


# ---------------------------------------------------------------------------
# cp1252 encoding
# ---------------------------------------------------------------------------


class TestCp1252:
    CP1252_ENV = {"PYTHONIOENCODING": "cp1252"}

    def test_demo_exits_zero_no_traceback(self, run: Harness):
        result = run.run("demo", env_overrides=self.CP1252_ENV)
        assert result.returncode == 0
        assert "Traceback" not in result.stderr

    def test_help_exits_zero_no_traceback(self, run: Harness):
        result = run.run("help", env_overrides=self.CP1252_ENV)
        assert result.returncode == 0
        assert "Traceback" not in result.stderr

    def test_about_spin_zero_exits_zero_no_traceback(self, run: Harness):
        result = run.run(
            "about", "--spin", "0", env_overrides=self.CP1252_ENV
        )
        assert result.returncode == 0
        assert "Traceback" not in result.stderr