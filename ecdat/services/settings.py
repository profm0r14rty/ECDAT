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
_DEFAULT_THEME = "ecdat-dark"

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
        theme: Preferred TUI theme name (e.g. ``"ecdat-dark"``).
        reduce_motion: Disable animations regardless of the environment.
        splash: Show the decrypt-reveal splash screen on TUI start.
    """

    migration_time_years: float = _DEFAULT_MIGRATION_YEARS
    shelf_life_years: float = _DEFAULT_SHELF_LIFE_YEARS
    threat_horizon_years: float = _DEFAULT_THREAT_HORIZON_YEARS
    theme: str = _DEFAULT_THEME
    reduce_motion: bool = False
    splash: bool = True


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_settings() -> AppSettings:
    """Load settings from disk, returning defaults when the file does not exist.

    Corrupt or unparseable files are silently replaced with defaults (the
    on-disk file is NOT mutated).  Unknown keys are ignored and a wrong-typed
    value falls back to that field's default without discarding the rest.

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

    if not isinstance(data, dict):
        return AppSettings()

    return AppSettings(
        migration_time_years=_as_float(
            data.get("migration_time_years"), _DEFAULT_MIGRATION_YEARS
        ),
        shelf_life_years=_as_float(
            data.get("shelf_life_years"), _DEFAULT_SHELF_LIFE_YEARS
        ),
        threat_horizon_years=_as_float(
            data.get("threat_horizon_years"), _DEFAULT_THREAT_HORIZON_YEARS
        ),
        theme=_as_str(data.get("theme"), _DEFAULT_THEME),
        reduce_motion=_as_bool(data.get("reduce_motion"), False),
        splash=_as_bool(data.get("splash"), True),
    )


def _as_float(value: object, default: float) -> float:
    """Return *value* as a float, or *default* when it is not numeric."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    return float(value)


def _as_str(value: object, default: str) -> str:
    """Return *value* as a non-empty string, or *default* otherwise."""
    if isinstance(value, str) and value.strip():
        return value
    return default


def _as_bool(value: object, default: bool) -> bool:
    """Return *value* as a bool, or *default* when it is not a bool."""
    if isinstance(value, bool):
        return value
    return default


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
        "theme": settings.theme,
        "reduce_motion": settings.reduce_motion,
        "splash": settings.splash,
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


def try_save_settings(settings: AppSettings) -> bool:
    """Save *settings* without raising.

    The UI must never crash because a settings write failed, so this wraps
    :func:`save_settings` and reports success as a boolean.

    Returns:
        ``True`` when the settings were persisted.
    """
    try:
        save_settings(settings)
    except OSError:
        return False
    return True
