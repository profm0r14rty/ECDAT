"""The ECDAT Textual application.

This is the TUI foundation: an :class:`~textual.app.App` with the ECDAT theme
pair, a Home screen, and bindings for theme cycling and help.  The real scan
screens arrive in later phases; :meth:`EcdatApp.start_scan` is wired to notify
so the Home screen can be exercised end-to-end today.

``run_tui`` refuses to start on a non-interactive terminal (returning ``2``
with a friendly message) so piping ``ecdat tui`` never hangs.
"""

from __future__ import annotations

import os
import sys
from typing import Optional

from textual.app import App

from ecdat.services.settings import try_save_settings
from ecdat.tui.theme import THEME_NAMES, register_themes

# The console entry point and Textual's own default.
_TITLE = "ECDAT"
_SUB_TITLE = "Post-quantum readiness scanner"


class EcdatApp(App[int]):
    """The top-level ECDAT Textual application."""

    TITLE = _TITLE
    SUB_TITLE = _SUB_TITLE
    CSS_PATH = "ecdat.tcss"

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("t", "cycle_theme", "Theme"),
        ("question_mark", "show_help", "Help"),
    ]

    def __init__(
        self,
        initial_target: Optional[str] = None,
        auto_start: bool = False,
        *,
        show_splash: bool = True,
    ) -> None:
        super().__init__()
        self.initial_target = initial_target
        self.auto_start = auto_start
        self.show_splash = show_splash
        # Themes must be registered before the stylesheet resolves $risk-*
        # variables, which happens before on_mount.
        register_themes(self)
        saved = self._saved_theme()
        self.theme = saved if saved in self.available_themes else THEME_NAMES[0]

    def on_mount(self) -> None:
        """Push the Home screen, then the splash on top of it when enabled."""
        from ecdat.tui.screens.home import HomeScreen
        from ecdat.tui.screens.splash import SplashScreen

        self.push_screen(HomeScreen())
        if self.show_splash and self._animations_on():
            # Pushed last so it sits on top of Home and dismisses to reveal it.
            self.push_screen(SplashScreen())

        if self.auto_start and self.initial_target:
            self.start_scan(self.initial_target)

    def _animations_on(self) -> bool:
        from ecdat.ui import motion

        return motion.animations_enabled(self._reduce_motion())

    def _reduce_motion(self) -> bool:
        from ecdat.services.settings import load_settings

        return load_settings().reduce_motion

    def _saved_theme(self) -> str:
        from ecdat.services.settings import load_settings

        return load_settings().theme

    def action_cycle_theme(self) -> None:
        """Cycle through every available theme and persist the choice."""
        available = list(self.available_themes)
        if not available:
            return
        try:
            index = available.index(self.theme)
        except ValueError:
            index = -1
        self.theme = available[(index + 1) % len(available)]
        self._persist_theme(self.theme)

    def _persist_theme(self, name: str) -> None:
        from ecdat.services.settings import load_settings

        settings = load_settings()
        settings.theme = name
        try_save_settings(settings)

    def action_show_help(self) -> None:
        """Placeholder help until the help screen lands."""
        self.notify(
            "Help arrives in a later phase — try q to quit, t to change theme.",
            title="ECDAT",
        )

    def start_scan(self, target: str, label: Optional[str] = None) -> None:
        """Begin a scan for *target* (stub until the scan screen lands)."""
        self.notify(f"scan: {target}", title=label or "ECDAT")

    def run_demo(self) -> None:
        """Scan the bundled demo project (stub until the scan screen lands)."""
        from ecdat.services.demo import demo_source

        source = demo_source()
        self.start_scan(str(source), label="demo project (bundled sample)")

    def open_history_entry(self, scan_id: str) -> None:
        """Open a saved scan (stub until the history screen lands)."""
        self.notify(f"history: {scan_id}", title="ECDAT")


def run_tui(
    target: Optional[str] = None,
    *,
    auto_start: bool = False,
    no_anim: bool = False,
    no_splash: bool = False,
) -> int:
    """Run the ECDAT TUI, or explain why it cannot start.

    Args:
        target: Optional scan target to pre-fill / auto-start.
        auto_start: Start scanning *target* immediately on mount.
        no_anim: Disable animation for this run (sets ``ECDAT_ANIM=0``).
        no_splash: Skip the splash screen for this run.

    Returns:
        ``0`` after a normal exit; ``2`` when stdin/stdout is not a TTY or
        ``TERM=dumb``.
    """
    if not _is_interactive():
        sys.stderr.write(
            "The TUI needs an interactive terminal \u2014 "
            "use `ecdat scan` instead.\n"
        )
        return 2

    if no_anim:
        os.environ["ECDAT_ANIM"] = "0"

    app = EcdatApp(target, auto_start=auto_start, show_splash=not no_splash)
    app.run()
    return 0


def _is_interactive() -> bool:
    """Return whether both stdin and stdout are attached to a terminal."""
    try:
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            return False
    except (AttributeError, ValueError):
        return False
    return os.environ.get("TERM", "").strip().lower() != "dumb"


__all__ = ["EcdatApp", "run_tui"]
