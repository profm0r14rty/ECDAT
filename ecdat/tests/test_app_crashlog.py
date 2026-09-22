"""Tests for :mod:`ecdat.services.crashlog` and :mod:`ecdat.services.paths`."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from ecdat.services import crashlog, paths


# ---------------------------------------------------------------------------
# paths
# ---------------------------------------------------------------------------


class TestPaths:
    """home_dir()/logs_dir() resolution rules."""

    def test_ecdat_home_override_wins(self):
        assert paths.home_dir() == Path(os.environ["ECDAT_HOME"])

    def test_logs_dir_under_home(self):
        assert paths.logs_dir() == paths.home_dir() / "logs"

    def test_helpers_do_not_create_directories(self):
        # The autouse fixture creates ECDAT_HOME itself, but the pure path
        # helpers must not create the logs subdirectory merely by being called.
        logs = Path(os.environ["ECDAT_HOME"]) / "logs"
        assert not logs.exists()
        paths.home_dir()
        paths.logs_dir()
        assert not logs.exists()

    def test_linux_xdg_data_home(self, monkeypatch):
        monkeypatch.delenv("ECDAT_HOME", raising=False)
        monkeypatch.setenv("XDG_DATA_HOME", "/custom/xdg")
        monkeypatch.setattr(sys, "platform", "linux")
        assert paths.home_dir() == Path("/custom/xdg") / "ecdat"

    def test_linux_default(self, monkeypatch, tmp_path):
        monkeypatch.delenv("ECDAT_HOME", raising=False)
        monkeypatch.delenv("XDG_DATA_HOME", raising=False)
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
        monkeypatch.setattr(sys, "platform", "linux")
        assert paths.home_dir() == tmp_path / ".local" / "share" / "ecdat"

    def test_darwin(self, monkeypatch, tmp_path):
        monkeypatch.delenv("ECDAT_HOME", raising=False)
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
        monkeypatch.setattr(sys, "platform", "darwin")
        assert paths.home_dir() == (
            tmp_path / "Library" / "Application Support" / "ecdat"
        )

    def test_windows_local_appdata(self, monkeypatch, tmp_path):
        monkeypatch.delenv("ECDAT_HOME", raising=False)
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
        monkeypatch.setattr(sys, "platform", "win32")
        assert paths.home_dir() == tmp_path / "ecdat"


# ---------------------------------------------------------------------------
# crashlog
# ---------------------------------------------------------------------------


def _raise(exc: BaseException) -> None:
    raise exc


class TestWriteCrashLog:
    """write_crash_log behaviour and retention."""

    def _write(self, message: str = "boom", argv=("scan", ".")):
        try:
            _raise(RuntimeError(message))
        except RuntimeError as exc:
            return crashlog.write_crash_log(exc, list(argv))
        raise AssertionError("unreachable")

    def test_returns_path_inside_logs_dir(self):
        path = self._write()
        assert path is not None
        assert path.exists()
        assert path.parent == paths.logs_dir()
        assert path.name.startswith("crash-")
        assert path.name.endswith(".log")

    def test_report_contents(self):
        path = self._write("unique-crash-marker", argv=("scan", "/some/path"))
        assert path is not None
        text = path.read_text(encoding="utf-8")
        assert "ECDAT crash report" in text
        assert "ecdat:" in text
        assert "python:" in text
        assert "platform:" in text
        assert "argv:" in text
        assert "'/some/path'" in text
        assert "RuntimeError: unique-crash-marker" in text
        assert "Traceback (most recent call last)" in text

    def test_never_raises_when_logs_dir_unavailable(self, monkeypatch):
        def _boom():
            raise OSError("no data dir for you")

        monkeypatch.setattr(crashlog, "logs_dir", _boom)
        try:
            _raise(ValueError("x"))
        except ValueError as exc:
            assert crashlog.write_crash_log(exc, ["scan"]) is None

    def test_keeps_newest_20(self):
        returned = [self._write(f"crash-{i}") for i in range(25)]
        logs = sorted(paths.logs_dir().glob("crash-*.log"))
        assert len(logs) == 20

        # The first five writes were evicted; the newest is present.
        for stale in returned[:5]:
            assert not stale.exists()
        for fresh in returned[-5:]:
            assert fresh.exists()

    def test_crash_logs_are_unique(self):
        paths_written = {self._write(f"c-{i}") for i in range(10)}
        assert len(paths_written) == 10
        assert all(p is not None for p in paths_written)
