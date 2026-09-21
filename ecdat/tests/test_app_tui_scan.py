"""Tests for the ScanScreen (Phase 83).

Headless Pilot tests with animations disabled (the repo's autouse ``ECDAT_ANIM``
fixture).  The engine scan itself is monkeypatched wherever timing would make a
test flaky; one real end-to-end scan against the bundled ``demo_repo`` fixture
proves the wiring.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest
from textual.widgets import Static

from ecdat.services import scanner as scanner_mod
from ecdat.services.scanner import ScanError, ScanOutcome, classify_target, perform_scan
from ecdat.tui.app import EcdatApp
from ecdat.tui.screens.home import HomeScreen
from ecdat.tui.screens.results import ResultsScreen
from ecdat.tui.screens.scan import ScanScreen
from ecdat_core.progress import ScanCancelled, ScanProgress

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tui_helpers import wait_until  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO_REPO = REPO_ROOT / "ecdat_core" / "tests" / "fixtures" / "demo_repo"


def _outcome() -> ScanOutcome:
    return perform_scan(classify_target(str(DEMO_REPO)), label="demo_repo")


async def _wait_for_results(pilot, app, timeout: float = 30.0) -> ResultsScreen:
    return await wait_until(
        pilot,
        lambda: app.screen if isinstance(app.screen, ResultsScreen) else None,
        timeout=timeout,
    )


# ---------------------------------------------------------------------------
# Real end-to-end scan
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scan_finishes_on_results_screen() -> None:
    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.start_scan(str(DEMO_REPO))
        await pilot.pause()
        assert isinstance(app.screen, ScanScreen)

        screen = await _wait_for_results(pilot, app)
        assert screen.vm.total > 0
        await pilot.pause(0.1)


@pytest.mark.asyncio
async def test_scan_screen_shows_torus_and_stages(monkeypatch) -> None:
    def fake_perform_scan(target, *, label=None, on_progress=None, **kw):
        for i in range(2_000):
            if on_progress is not None:
                on_progress(
                    ScanProgress(
                        stage="detect",
                        message="scanning",
                        current=i,
                        total=2_000,
                        detections=0,
                    )
                )
            time.sleep(0.002)
        return _outcome()

    monkeypatch.setattr(scanner_mod, "perform_scan", fake_perform_scan)

    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        screen = ScanScreen(str(DEMO_REPO), label="demo_repo")
        app.push_screen(screen)
        await pilot.pause()
        assert screen.query_one("#scan-torus") is not None
        assert screen.query_one("#stage-clone", Static).display is False
        assert screen.query_one("#stage-detect") is not None

        await pilot.press("escape")
        await wait_until(
            pilot, lambda: isinstance(app.screen, HomeScreen), timeout=15.0
        )


# ---------------------------------------------------------------------------
# Error path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scan_error_shows_panel_and_retry(monkeypatch) -> None:
    calls: list[object] = []

    def fake_perform_scan(target, *, label=None, on_progress=None, **kw):
        calls.append(target)
        raise ScanError("simulated failure", hint="try the other folder")

    monkeypatch.setattr(scanner_mod, "perform_scan", fake_perform_scan)

    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.start_scan(str(DEMO_REPO))
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, ScanScreen)

        await wait_until(
            pilot,
            lambda: screen.query_one("#scan-error", Static).display,
            timeout=10.0,
        )
        assert len(calls) == 1

        await pilot.press("r")
        await wait_until(pilot, lambda: len(calls) >= 2, timeout=10.0)
        assert len(calls) == 2


# ---------------------------------------------------------------------------
# Cancellation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_escape_cancels_scan_and_returns_home(monkeypatch) -> None:
    started = {"value": False}

    def fake_perform_scan(target, *, label=None, on_progress=None, **kw):
        started["value"] = True
        # Bounded so a broken cancel fails the test instead of hanging: the
        # screen's callback raises ScanCancelled once Escape is pressed.
        for i in range(2_000):
            if on_progress is not None:
                on_progress(
                    ScanProgress(
                        stage="detect",
                        message="scanning",
                        current=i,
                        total=2_000,
                        detections=0,
                    )
                )
            time.sleep(0.002)
        return _outcome()

    monkeypatch.setattr(scanner_mod, "perform_scan", fake_perform_scan)

    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.start_scan(str(DEMO_REPO))
        await wait_until(pilot, lambda: started["value"], timeout=10.0)

        await pilot.press("escape")
        await wait_until(
            pilot, lambda: isinstance(app.screen, HomeScreen), timeout=15.0
        )


def test_callback_raises_scan_cancelled_when_event_set() -> None:
    """The worker callback raises ScanCancelled once the cancel event is set."""
    screen = ScanScreen(str(DEMO_REPO), label="demo_repo")
    screen._cancel.set()
    with pytest.raises(ScanCancelled):
        screen._deliver_or_raise(
            ScanProgress(stage="detect", message="x", current=1, total=10, detections=0)
        )


# ---------------------------------------------------------------------------
# Demo mode and git targets
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_demo_binding_reaches_results() -> None:
    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.set_focus(None)
        await pilot.press("d")
        await pilot.pause()
        assert isinstance(app.screen, ScanScreen)

        screen = await _wait_for_results(pilot, app, timeout=30.0)
        # The demo project is the packaged showcase copy: 70 artefacts.
        assert screen.vm.total == 70
        await pilot.pause(0.1)


@pytest.mark.asyncio
async def test_git_target_shows_clone_stage(monkeypatch) -> None:
    def fake_perform_scan(target, *, label=None, on_progress=None, **kw):
        return _outcome()

    monkeypatch.setattr(scanner_mod, "perform_scan", fake_perform_scan)

    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        screen = ScanScreen("https://github.com/example/repo")
        app.push_screen(screen)
        await pilot.pause()
        assert screen.query_one("#stage-clone", Static).display is True

        await _wait_for_results(pilot, app)
        await pilot.pause(0.1)


# ---------------------------------------------------------------------------
# Throttling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_progress_updates_are_throttled(monkeypatch) -> None:
    outcome = _outcome()
    emitted = 10_000

    def fake_perform_scan(target, *, label=None, on_progress=None, **kw):
        for i in range(emitted):
            if on_progress is not None:
                on_progress(
                    ScanProgress(
                        stage="detect",
                        message="scanning",
                        current=i,
                        total=emitted,
                        detections=0,
                    )
                )
            time.sleep(0.0001)
        return outcome

    monkeypatch.setattr(scanner_mod, "perform_scan", fake_perform_scan)

    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        screen = ScanScreen(str(DEMO_REPO), label="demo_repo")
        app.push_screen(screen)
        await _wait_for_results(pilot, app)
        assert screen._ui_updates < 500
        await pilot.pause(0.1)
