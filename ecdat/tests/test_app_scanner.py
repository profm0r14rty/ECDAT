"""Tests for ecdat.services.scanner."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from ecdat_core.models import ScanResult
from ecdat.services.scanner import (
    ScanError,
    ScanOutcome,
    Target,
    classify_target,
    perform_scan,
)

DEMO_REPO = (
    Path(__file__).resolve().parents[2]
    / "ecdat_core"
    / "tests"
    / "fixtures"
    / "demo_repo"
)

# Minimal ScanResult for mocking
MOCK_SCAN_RESULT = ScanResult(
    scan_id="test-scan-id",
    target="mock-target",
    detections=[],
    risk_assessments=[],
    recommendations=[],
    scanned_at="2024-01-01T00:00:00+00:00",
    files_scanned=0,
)


# ---------------------------------------------------------------------------
# classify_target table
# ---------------------------------------------------------------------------


class TestClassifyTarget:
    """Table-driven classify_target tests."""

    def test_https_url_accepted(self):
        target = classify_target("https://github.com/user/repo.git")
        assert target.kind == "git"
        assert target.value == "https://github.com/user/repo.git"

    def test_http_rejected(self):
        with pytest.raises(ScanError) as exc:
            classify_target("http://github.com/user/repo.git")
        assert exc.value.exit_code == 2
        assert "Only https://" in exc.value.user_message

    def test_ssh_url_rejected(self):
        with pytest.raises(ScanError) as exc:
            classify_target("ssh://git@github.com/user/repo.git")
        assert exc.value.exit_code == 2

    def test_git_url_rejected(self):
        with pytest.raises(ScanError) as exc:
            classify_target("git://github.com/user/repo.git")
        assert exc.value.exit_code == 2

    def test_git_at_scp_style_rejected(self):
        with pytest.raises(ScanError) as exc:
            classify_target("git@github.com:user/repo.git")
        assert exc.value.exit_code == 2
        assert "Only https://" in exc.value.user_message

    def test_file_url_rejected(self):
        with pytest.raises(ScanError) as exc:
            classify_target("file:///etc/passwd")
        assert exc.value.exit_code == 2

    def test_dot_local(self):
        target = classify_target(".")
        assert target.kind == "local"

    def test_tilde_local(self):
        target = classify_target("~")
        assert target.kind == "local"

    def test_missing_path_error(self):
        with pytest.raises(ScanError) as exc:
            classify_target("/nonexistent/path/xyz123")
        assert exc.value.exit_code == 2
        assert "Path does not exist" in exc.value.user_message

    def test_file_not_dir_error(self):
        with tempfile.NamedTemporaryFile() as tf:
            with pytest.raises(ScanError) as exc:
                classify_target(tf.name)
            assert exc.value.exit_code == 2
            assert "Not a directory" in exc.value.user_message

    def test_windows_drive_path_is_local(self):
        # On Linux a Windows-style path won't exist, but it MUST be classified
        # as local (not git).  The error message proves it took the local path.
        with pytest.raises(ScanError) as exc:
            classify_target("C:\\Users\\x")
        assert exc.value.exit_code == 2
        assert "Path does not exist" in exc.value.user_message
        # Must NOT mention git — that would mean it was misclassified as a URL.
        assert "git" not in exc.value.user_message.lower()
        assert "https" not in exc.value.user_message.lower()

    def test_empty_string_raises(self):
        with pytest.raises(ScanError) as exc:
            classify_target("")
        assert exc.value.exit_code == 2

    def test_whitespace_only_raises(self):
        with pytest.raises(ScanError) as exc:
            classify_target("   ")
        assert exc.value.exit_code == 2

    def test_force_git_https_ok(self):
        target = classify_target("https://github.com/user/repo.git", force_git=True)
        assert target.kind == "git"

    def test_force_git_http_rejected(self):
        with pytest.raises(ScanError) as exc:
            classify_target("http://github.com/user/repo.git", force_git=True)
        assert exc.value.exit_code == 2

    def test_force_git_file_url_rejected(self):
        with pytest.raises(ScanError) as exc:
            classify_target("file:///etc/passwd", force_git=True)
        assert exc.value.exit_code == 2

    def test_demo_repo_is_local(self):
        target = classify_target(str(DEMO_REPO))
        assert target.kind == "local"
        assert Path(target.value).is_dir()


# ---------------------------------------------------------------------------
# perform_scan — monkeypatched run_scan
# ---------------------------------------------------------------------------


class TestPerformScanMonkeypatched:
    """perform_scan delegates correctly to run_scan."""

    def test_git_url_passes_is_git_url_true(self):
        with patch("ecdat.services.scanner.run_scan") as mock_run:
            mock_run.return_value = MOCK_SCAN_RESULT
            target = Target(
                kind="git",
                value="https://example.com/repo",
                display="https://example.com/repo",
            )
            perform_scan(target)
            mock_run.assert_called_once_with(
                "https://example.com/repo", is_git_url=True
            )

    def test_local_passes_sandboxed_false(self):
        with patch("ecdat.services.scanner.run_scan") as mock_run:
            mock_run.return_value = MOCK_SCAN_RESULT
            target = Target(kind="local", value="/some/path", display="/some/path")
            perform_scan(target)
            mock_run.assert_called_once_with("/some/path", sandboxed=False)

    def test_label_overrides_target_display(self):
        with patch("ecdat.services.scanner.run_scan") as mock_run:
            mock_run.return_value = MOCK_SCAN_RESULT
            target = Target(kind="local", value="/some/path", display="/some/path")
            outcome = perform_scan(target, label="custom-label")
            assert outcome.vm.target == "custom-label"

    def test_target_display_used_when_label_is_none(self):
        with patch("ecdat.services.scanner.run_scan") as mock_run:
            mock_run.return_value = MOCK_SCAN_RESULT
            target = Target(kind="local", value="/some/path", display="my display")
            outcome = perform_scan(target, label=None)
            assert outcome.vm.target == "my display"


# ---------------------------------------------------------------------------
# perform_scan — real scan (local only, no network)
# ---------------------------------------------------------------------------


class TestPerformScanLocal:
    """perform_scan with real local directory scans."""

    def test_scan_demo_repo_succeeds(self):
        target = Target(kind="local", value=str(DEMO_REPO), display=str(DEMO_REPO))
        outcome = perform_scan(target)

        assert isinstance(outcome.result, ScanResult)
        assert outcome.vm.total == len(outcome.result.detections)
        assert outcome.duration_s is not None
        assert isinstance(outcome.duration_s, float)

    def test_scan_empty_dir_succeeds(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Target(kind="local", value=tmpdir, display=tmpdir)
            outcome = perform_scan(target)

            assert outcome.vm.total == 0
            assert outcome.vm.safe_ratio == 0.0
            assert outcome.duration_s >= 0

    def test_scan_non_existent_path_raises_scanerror(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            nonexistent = str(Path(tmpdir) / "does-not-exist")
            target = Target(kind="local", value=nonexistent, display=nonexistent)
            with pytest.raises(ScanError) as exc:
                perform_scan(target)
            assert exc.value.exit_code == 3
            assert "Scan failed" in exc.value.user_message


# ---------------------------------------------------------------------------
# Real git clone — requires network
# ---------------------------------------------------------------------------


@pytest.mark.network
class TestPerformScanGit:
    """perform_scan with a real remote git clone."""

    def test_real_git_clone_small_repo(self):
        target = Target(
            kind="git",
            value="https://github.com/octocat/Hello-World.git",
            display="https://github.com/octocat/Hello-World.git",
        )
        outcome = perform_scan(target)
        assert isinstance(outcome.result, ScanResult)
        assert outcome.duration_s is not None
        assert isinstance(outcome.duration_s, float)
        assert outcome.vm is not None