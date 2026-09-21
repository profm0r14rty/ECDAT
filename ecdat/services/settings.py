"""ECDAT application settings.

A simple file-backed settings store for the CLI scanner.  Reads/writes a
JSON file at the path returned by :func:`ecdat.services.paths.settings_file`.

Public API:
    - :class:`AppSettings` — dataclass holding editable parameters.
    - :func:`load_settings` — load from disk (or return defaults).
    - :func:`save_settings` — atomically write to disk.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ecdat.services.paths import settings_file


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

_DEFAULT_MIGRATION_YEARS = 5.0
_DEFAULT_SHELF_LIFE_YEARS = 10.0
_DEFAULT_THREAT_HORIZON_YEARS = 10.0

# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------


@dataclass
class AppSettings:
    """Editable application settings for the ECDAT CLI.

    Attributes:
        migration_time_years: Default migration time (X in Mosca).
        shelf_life_years: Default data shelf-life (Y in Mosca).
        threat_horizon_years: Default quantum threat horizon (Z in Mosca).
    """

    migration_time_years: float = _DEFAULT_MIGRATION_YEARS
    shelf_life_years: float = _DEFAULT_SHELF_LIFE_YEARS
    threat_horizon_years: float = _DEFAULT_THREAT_HORIZON_YEARS


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_settings() -> AppSettings:
    """Load settings from disk, returning defaults when the file does not exist.

    Corrupt or unparseable files are silently replaced with defaults (the
    on-disk file is NOT mutated).

    Returns:
        An :class:`AppSettings` instance.
    """
    path = settings_file()
    if not path.exists():
        return AppSettings()

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return AppSettings()

    return AppSettings(
        migration_time_years=float(
            data.get("migration_time_years", _DEFAULT_MIGRATION_YEARS)
        ),
        shelf_life_years=float(
            data.get("shelf_life_years", _DEFAULT_SHELF_LIFE_YEARS)
        ),
        threat_horizon_years=float(
            data.get("threat_horizon_years", _DEFAULT_THREAT_HORIZON_YEARS)
        ),
    )


def save_settings(settings: AppSettings) -> None:
    """Atomically save *settings* to disk.

    Writes to a temporary file in the destination directory, then renames
    it over the target, so a crash mid-write never leaves a corrupt file.

    Args:
        settings: The settings to persist.

    Raises:
        OSError: If the parent directory cannot be created or the write fails.
    """
    path = settings_file()
    path.parent.mkdir(parents=True, exist_ok=True)

    payload: dict = {
        "migration_time_years": settings.migration_time_years,
        "shelf_life_years": settings.shelf_life_years,
        "threat_horizon_years": settings.threat_horizon_years,
    }

    # Atomic write: write to a temp file, then rename.
    fd, tmp_path = tempfile.mkstemp(
        suffix=".json", prefix=".settings-", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, sort_keys=True)
            f.write("\n")
        os.replace(tmp_path, str(path))
    except BaseException:
        # Clean up the temp file on any error.
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise