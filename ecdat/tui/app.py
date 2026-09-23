"""The ECDAT Textual application.

:class:`EcdatApp` owns the ECDAT theme pair, the global bindings (quit, theme
cycling, help), the command palette, and the terminal-health guards — a
full-screen "enlarge your terminal" overlay below 80×24 and a one-time tip on
16/8-colour terminals.

The real scan screens (Home, Scan, Results, Export, History, Help) are pushed
from here; :meth:`EcdatApp.start_scan`, :meth:`EcdatApp.run_demo` and
:meth:`EcdatApp.open_history_entry` are the entry points the screens call back
into.

``run_tui`` refuses to start on a non-interactive terminal (returning ``2``
with a friendly message) so piping ``ecdat tui`` never hangs, and it converts
an unexpected crash into a crash-log entry plus a friendly message instead of
a raw traceback.
"""

from __future__ import annotations

import os
import sys
from typing import Iterable, Optional

from textual.app import App, ComposeResult
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Static

from rich.text import Text

from ecdat.services.settings import try_save_settings
from ecdat.tui.theme import THEME_NAMES, register_themes, risk_variable_defaults

# The console entry point and Textual's own default.
_TITLE = "ECDAT"
_SUB_TITLE = "Post-quantum readiness scanner"

# Below this the layout is unusable, so the guard takes over the screen.
_MIN_COLUMNS = 80
_MIN_ROWS = 24

_TRUECOLOR_HINT = (
    "For the best look use a truecolor terminal (COLORTERM=truecolor)."
)


class TooSmallScreen(Screen[None]):
    """A full-screen overlay shown while the terminal is below the minimum size.

    Pushed by :class:`EcdatApp` on resize when the terminal is narrower than
    80 columns or shorter than 24 rows, and popped again as soon as the
    terminal grows back.
    """

    BINDINGS = [("q", "quit_app", "Quit")]

    def compose(self) -> ComposeResult:
        with Vertical(id="too-small-body"):
            yield Static(
                Text(
                    "Please enlarge the terminal to at least 80\u00d724",
                    style="bold",
                ),
                id="too-small-message",
            )
            yield Static(
                Text("ECDAT needs a little more room.", style="dim"),
                id="too-small-hint",
            )

    def action_quit_app(self) -> None:
        """Quit the app from the guard overlay."""
        self.app.exit()


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
        demo: bool = False,
    ) -> None:
        super().__init__()
        self.initial_target = initial_target
        self.auto_start = auto_start
        self.show_splash = show_splash
        self.demo = demo
        self._shown_truecolor_hint = False
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
        # Only push the splash when nothing else is about to be pushed on top
        # of it in this same on_mount tick. A demo run or an auto-start scan
        # pushes a second screen immediately, which would leave the splash
        # buried; its auto-dismiss timer would then fire while that screen is
        # on top. (``SplashScreen`` additionally refuses to pop a screen it no
        # longer owns, but not pushing it at all is the cleaner precondition.)
        launches_second_screen = self.demo or (
            self.auto_start and self.initial_target
        )
        if (
            self.show_splash
            and self._animations_on()
            and not launches_second_screen
        ):
            # Pushed last so it sits on top of Home and dismisses to reveal it.
            self.push_screen(SplashScreen())

        self._enforce_minimum_size()
        self.call_after_refresh(self._maybe_show_truecolor_hint)

        if self.demo:
            self.run_demo()
        elif self.auto_start and self.initial_target:
            self.start_scan(self.initial_target)

    # -- terminal guards ----------------------------------------------------

    def on_resize(self, event) -> None:  # noqa: ANN001 - Textual event
        """Push or pop the too-small overlay as the terminal changes size."""
        self._enforce_minimum_size(event.size.width, event.size.height)

    def _enforce_minimum_size(
        self, width: Optional[int] = None, height: Optional[int] = None
    ) -> None:
        """Show the guard overlay when the terminal is too small, else hide it.

        Bookkeeping checks the *actual* top screen rather than a flag, so a
        screen switch (e.g. a scan finishing) can never desynchronise it.
        """
        if not self.is_running or self.screen is None:
            return
        size = self.screen.size
        if width is None:
            width = size.width
        if height is None:
            height = size.height

        showing = isinstance(self.screen, TooSmallScreen)
        too_small = width < _MIN_COLUMNS or height < _MIN_ROWS

        if too_small and not showing:
            self.push_screen(TooSmallScreen())
        elif not too_small and showing:
            self.pop_screen()

    def _maybe_show_truecolor_hint(self) -> None:
        """On a low-colour terminal, show a one-time dim truecolour tip."""
        if self._shown_truecolor_hint:
            return
        color_system = getattr(self.console, "color_system", None)
        if color_system in (None, "standard", "windows"):
            self._shown_truecolor_hint = True
            self.notify(
                Text(_TRUECOLOR_HINT, style="dim"),
                title="ECDAT",
                timeout=8,
            )

    # -- settings / animation -----------------------------------------------

    def _animations_on(self) -> bool:
        from ecdat.ui import motion

        return motion.animations_enabled(self._reduce_motion())

    def _reduce_motion(self) -> bool:
        from ecdat.services.settings import load_settings

        return load_settings().reduce_motion

    def _saved_theme(self) -> str:
        from ecdat.services.settings import load_settings

        return load_settings().theme

    # -- theme --------------------------------------------------------------

    def get_theme_variable_defaults(self) -> dict[str, str]:
        """Make the ``$risk-*`` variables resolve under *any* active theme.

        Textual builds the stylesheet's variable set inside ``App.__init__``
        (before the ECDAT themes are registered or the saved theme applied),
        and re-resolves it on every theme switch.  The base default is empty,
        and Textual's built-in themes (``textual-dark``/``textual-light``)
        define no ``risk-*`` variables — so a saved built-in theme (or
        cycling ``t`` into one) would raise ``UnresolvedVariableError`` at
        parse time.  Supplying the risk colours here means ``ecdat.tcss``
        parses under every theme; each theme's own ``variables`` still take
        precedence over these defaults when it is active.
        """
        defaults = dict(super().get_theme_variable_defaults())
        defaults.update(risk_variable_defaults())
        return defaults

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

    # -- help ---------------------------------------------------------------

    def action_show_help(self) -> None:
        """Open the keyboard-help overlay."""
        from ecdat.tui.screens.help import HelpScreen

        self.push_screen(HelpScreen())

    # -- command palette ----------------------------------------------------

    def get_system_commands(self, screen) -> Iterable:  # noqa: ANN001
        """Yield Textual's built-in commands plus ECDAT's own.

        Keeps every built-in system command (theme, screenshot, quit, …) and
        adds the app-level actions a user expects from ``ctrl+p``.  "Export
        results" is offered only while the Results screen is active, because
        there is nothing to export elsewhere.
        """
        from textual.app import SystemCommand

        yield from super().get_system_commands(screen)

        from ecdat.tui.screens.results import ResultsScreen

        yield SystemCommand(
            "New scan",
            "Go back to Home and start a new scan",
            self.action_new_scan,
        )
        yield SystemCommand(
            "Run demo",
            "Scan the bundled demo project",
            self.run_demo,
        )
        yield SystemCommand(
            "Recent scans",
            "Browse saved scans",
            self.action_open_history,
        )
        if isinstance(screen, ResultsScreen):
            yield SystemCommand(
                "Export results",
                "Write CBOM / summary / Markdown / HTML files",
                self.action_export_results,
            )
        yield SystemCommand(
            "Cycle theme",
            "Switch between the ECDAT colour themes",
            self.action_cycle_theme,
        )
        yield SystemCommand(
            "Toggle animations",
            "Turn animations on or off (remembered)",
            self.action_toggle_animations,
        )
        yield SystemCommand(
            "Show keyboard help",
            "Open the keyboard reference",
            self.action_show_help,
        )

    def action_new_scan(self) -> None:
        """Return to the Home screen."""
        from ecdat.tui.screens.home import HomeScreen

        self.switch_screen(HomeScreen())

    def action_open_history(self) -> None:
        """Open the History screen."""
        self.open_history_entry("latest")

    def action_export_results(self) -> None:
        """Ask the active Results screen to open its export dialog."""
        exporter = getattr(self.screen, "action_export_result", None)
        if callable(exporter):
            exporter()
        else:
            self.notify("Open a scan result first to export it.", title="ECDAT")

    def action_toggle_animations(self) -> None:
        """Flip ``reduce_motion``, persist it, and tell the user to restart."""
        from ecdat.services.settings import load_settings

        settings = load_settings()
        settings.reduce_motion = not settings.reduce_motion
        try_save_settings(settings)
        state = "off" if settings.reduce_motion else "on"
        self.notify(
            f"Animations {state} \u2014 restart the view to apply",
            title="ECDAT",
        )

    # -- navigation ---------------------------------------------------------

    def start_scan(self, target: str, label: Optional[str] = None) -> None:
        """Push the live scan screen for *target*.

        Args:
            target: A local folder path or an ``https://`` Git URL.
            label: Optional display label (e.g. "demo project"); defaults to
                *target* on the scan screen.
        """
        from ecdat.tui.screens.scan import ScanScreen

        self.push_screen(ScanScreen(target, label))

    def run_demo(self) -> None:
        """Scan the bundled demo project on the live scan screen."""
        from ecdat.tui.screens.scan import ScanScreen

        self.push_screen(ScanScreen("", "demo project", demo=True))

    def open_history_entry(self, scan_id: str) -> None:
        """Open the History screen, or a specific saved scan.

        Args:
            scan_id: A scan id / unique id prefix to open directly, or
                ``"latest"``/``""`` to just show the History list.
        """
        from ecdat.tui.screens.history import HistoryScreen

        if scan_id in ("", "latest"):
            self.push_screen(HistoryScreen())
            return

        from ecdat.services.history import HistoryError, load_scan
        from ecdat.services.scanner import ScanOutcome
        from ecdat.services.viewmodel import build_scan_vm

        try:
            record = load_scan(scan_id)
        except HistoryError:
            self.notify(
                "That scan is no longer in history.", title="ECDAT"
            )
            self.push_screen(HistoryScreen())
            return

        vm = build_scan_vm(record, target=record.target, duration_s=None)
        outcome = ScanOutcome(
            result=record, vm=vm, duration_s=0.0, record_id=record.scan_id
        )
        from ecdat.tui.screens.results import ResultsScreen

        self.switch_screen(ResultsScreen(outcome))


def run_tui(
    target: Optional[str] = None,
    *,
    auto_start: bool = False,
    no_anim: bool = False,
    no_splash: bool = False,
    demo: bool = False,
) -> int:
    """Run the ECDAT TUI, or explain why it cannot start.

    Args:
        target: Optional scan target to pre-fill / auto-start.
        auto_start: Start scanning *target* immediately on mount.
        no_anim: Disable animation for this run (sets ``ECDAT_ANIM=0``).
        no_splash: Skip the splash screen for this run.
        demo: Start the bundled demo scan immediately on mount.

    Returns:
        ``0`` after a normal exit; ``2`` when stdin/stdout is not a TTY or
        ``TERM=dumb``; ``3`` on an unexpected crash; ``130`` on Ctrl-C.
    """
    if not _is_interactive():
        sys.stderr.write(
            "The TUI needs an interactive terminal \u2014 "
            "use `ecdat scan` instead.\n"
        )
        return 2

    if no_anim:
        os.environ["ECDAT_ANIM"] = "0"

    app = EcdatApp(
        target,
        auto_start=auto_start,
        show_splash=not no_splash,
        demo=demo,
    )
    try:
        app.run()
    except KeyboardInterrupt:
        return 130
    except Exception as exc:  # noqa: BLE001 - top-level TUI guard rail
        # Textual restores the terminal on its way out, so all that is left
        # is to record the crash and point the user at it.
        from ecdat.services.crashlog import write_crash_log

        log_path = write_crash_log(exc, list(sys.argv))
        details = str(log_path) if log_path is not None else "(crash log unavailable)"
        sys.stderr.write(
            f"ECDAT hit an unexpected error. Details: {details}. "
            f"Re-run with ECDAT_DEBUG=1 for the traceback and attach "
            f"`ecdat doctor` output to an issue.\n"
        )
        return 3
    return 0


def _is_interactive() -> bool:
    """Return whether both stdin and stdout are attached to a terminal."""
    try:
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            return False
    except (AttributeError, ValueError):
        return False
    return os.environ.get("TERM", "").strip().lower() != "dumb"


__all__ = ["EcdatApp", "TooSmallScreen", "run_tui"]
