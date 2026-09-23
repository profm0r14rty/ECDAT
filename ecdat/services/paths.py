"""Filesystem locations for ECDAT user data.

Pure, side-effect-free path computations — importing this module creates
nothing and touches nothing.  Directories are created lazily by whoever
writes (see :mod:`ecdat.services.history` and :mod:`ecdat.services.crashlog`).

Resolution order for :func:`home_dir`:

1. ``ECDAT_HOME`` (environment override — used by tests and advanced users).
2. Windows: ``%LOCALAPPDATA%\\ecdat``.
3. macOS: ``~/Library/Application Support/ecdat``.
4. Linux/other: ``$XDG_DATA_HOME/ecdat`` or ``~/.local/share/ecdat``.

:func:`get_ec_home` is kept as the app-layer alias used by the history and
settings stores; it resolves to exactly the same directory as
:func:`home_dir`.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

__all__ = [
    "home_dir",
    "get_ec_home",
    "logs_dir",
    "history_dir",
    "settings_file",
]


def home_dir() -> Path:
    """Return the ECDAT user-data root directory (not created).

    Returns:
        A :class:`~pathlib.Path` pointing at the app's data root.  The path
        may not exist yet — callers are responsible for creating it.
    """
    override = os.environ.get("ECDAT_HOME")
    if override:
        return Path(override).expanduser()

    if sys.platform.startswith("win"):
        local_appdata = os.environ.get("LOCALAPPDATA")
        if local_appdata:
            return Path(local_appdata) / "ecdat"
        return Path.home() / "AppData" / "Local" / "ecdat"

    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "ecdat"

    xdg_data_home = os.environ.get("XDG_DATA_HOME")
    if xdg_data_home:
        return Path(xdg_data_home) / "ecdat"
    return Path.home() / ".local" / "share" / "ecdat"


def get_ec_home() -> Path:
    """Return the ECDAT home directory (alias of :func:`home_dir`).

    Kept as the name the history/settings stores use.
    """
    return home_dir()


def logs_dir() -> Path:
    """Return the ECDAT logs directory (``home_dir()/logs``; not created)."""
    return home_dir() / "logs"


def history_dir() -> Path:
    """Return the scan history directory, creating it if necessary.

    Returns:
        ``home_dir()/history`` (created with ``parents=True``).
    """
    path = history_dir_path()
    path.mkdir(parents=True, exist_ok=True)
    return path


def history_dir_path() -> Path:
    """Return the scan history directory path without creating it."""
    return get_ec_home() / "history"


def settings_file() -> Path:
    """Return the path to the settings JSON file.

    Returns:
        ``home_dir()/settings.json``.  The containing directory is NOT
        created by this function.
    """
    return get_ec_home() / "settings.json"
