"""Tests for ecdat.services.settings."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from ecdat.services.paths import get_ec_home, settings_file
from ecdat.services.settings import AppSettings, load_settings, save_settings


@pytest.fixture(autouse=True)
def _isolate_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Redirect ECDAT_HOME to a non-existent subdirectory for every test."""
    monkeypatch.setenv("ECDAT_HOME", str(tmp_path / ".ecdat"))


# ---- get_ec_home -------------------------------------------------------


def test_get_ec_home_from_env() -> None:
    assert get_ec_home() == Path(os.environ["ECDAT_HOME"])


def test_get_ec_home_creates_nothing() -> None:
    """get_ec_home must not create the directory."""
    home = get_ec_home()
    assert not home.exists()


# ---- settings_file ------------------------------------------------------


def test_settings_file_in_ec_home() -> None:
    sf = settings_file()
    assert sf.parent == get_ec_home()
    assert sf.name == "settings.json"


# ---- load_settings - defaults -------------------------------------------


def test_load_defaults_when_no_file() -> None:
    s = load_settings()
    assert s.migration_time_years == 5.0
    assert s.shelf_life_years == 10.0
    assert s.threat_horizon_years == 10.0


def test_load_corrupt_file_returns_defaults() -> None:
    get_ec_home().mkdir(parents=True, exist_ok=True)
    settings_file().write_text("not json {{{", encoding="utf-8")
    s = load_settings()
    assert s.migration_time_years == 5.0


# ---- save + load roundtrip ----------------------------------------------


def test_save_and_load_roundtrip() -> None:
    s = AppSettings(
        migration_time_years=3.0,
        shelf_life_years=7.0,
        threat_horizon_years=12.0,
    )
    save_settings(s)
    loaded = load_settings()
    assert loaded.migration_time_years == 3.0
    assert loaded.shelf_life_years == 7.0
    assert loaded.threat_horizon_years == 12.0


def test_save_creates_parent_directory() -> None:
    home = get_ec_home()
    assert not home.exists()

    save_settings(AppSettings())
    assert home.exists()
    assert settings_file().exists()


def test_save_atomic_writes_valid_json() -> None:
    save_settings(AppSettings(migration_time_years=1.5))
    raw = json.loads(settings_file().read_text(encoding="utf-8"))
    assert raw["migration_time_years"] == 1.5
    assert "shelf_life_years" in raw
    assert "threat_horizon_years" in raw