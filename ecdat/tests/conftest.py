"""App-layer test fixtures — session-wide env setup."""

import os
import tempfile

import pytest


@pytest.fixture(autouse=True)
def ecdat_home_and_anim():
    """Set ECDAT_HOME to a temp dir and disable animations for every test."""
    with tempfile.TemporaryDirectory(prefix="ecdat-test-") as tmpdir:
        home = os.path.join(tmpdir, "ecdat-home")
        os.makedirs(home, exist_ok=True)
        os.environ["ECDAT_HOME"] = home
        os.environ["ECDAT_ANIM"] = "0"
        yield