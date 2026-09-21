"""ECDAT filesystem paths.

Centralises all path decisions so the rest of the app layer never
hard-codes ``~/.ecdat``, ``.ecdat/``, or any other path convention.

Public API:
    - :func:`get_ec_home` — return ``ECDAT_HOME`` (default ``~/.ecdat``).
    - :func:`history_dir` — ensure and return the history directory.
    - :func:`settings_file` — return path to ``settings.json``.
"""

from __future__ import annotations

import os
from pathlib import Path


def get_ec_home() -> Path:
    """Return the ECDAT home directory.

    Controlled by the ``ECDAT_HOME`` environment variable.  When unset,
    defaults to ``~/.ecdat``.

    Returns:
        Path to the ECDAT home directory (the directory itself is NOT
        created by this function — callers who need it to exist should
        call ``mkdir(parents=True, exist_ok=True)`` themselves).
    """
    env = os.environ.get("ECDAT_HOME")
    if env:
        return Path(env)
    return Path.home() / ".ecdat"


def history_dir() -> Path:
    """Return the scan history directory, creating it if necessary.

    Returns:
        ``EC_HOME/history`` (created with ``parents=True``).
    """
    p = get_ec_home() / "history"
    p.mkdir(parents=True, exist_ok=True)
    return p


def settings_file() -> Path:
    """Return the path to the settings JSON file.

    Returns:
        ``EC_HOME/settings.json``.  The containing directory is NOT
        created by this function.
    """
    return get_ec_home() / "settings.json"