"""The Home screen — the first thing people see.

Layout adapts to the terminal: wide terminals get a two-column hero (banner,
target input, menu, recents on the left; the hex-globe on the right), narrower
ones drop the globe, and very small ones hide it entirely via the ``-compact``
class.

Every untrusted string (scan targets, recent-scan targets, paths) enters a
widget only as :class:`rich.text.Text`, never as markup.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.validation import ValidationResult, Validator
from textual.widgets import Footer, Header, Input, OptionList, Static
from textual.widgets.option_list import Option

from ecdat.services.scanner import ScanError, classify_target
from ecdat.tui.screens.pick_dir import PickDirScreen
from ecdat.tui.widgets.art_view import ArtView
from ecdat.tui.widgets.banner import BannerWidget
from ecdat.ui.theme import strip_control_chars

# Breakpoints for the responsive hero.
_WIDE_COLS = 100
_WIDE_ROWS = 30
_NARROW_COLS = 72
_NARROW_ROWS = 28

# Menu ids.
_MENU_SCAN = "menu-scan"
_MENU_BROWSE = "menu-browse"
_MENU_DEMO = "menu-demo"
_MENU_RECENT = "menu-recent"
_MENU_HELP = "menu-help"
_MENU_QUIT = "menu-quit"

_INPUT_PLACEHOLDER = "Folder path or https:// Git URL — Enter to scan"


class TargetValidator(Validator):
    """Validate a scan-target string with :func:`classify_target`."""

    def validate(self, value: str) -> ValidationResult:
        """Return success when *value* classifies as a scannable target."""
        if not value.strip():
            return self.failure("Enter a folder path or https:// Git URL")
        try:
            classify_target(value)
        except ScanError as exc:
            return self.failure(exc.user_message)
        return self.success()


class HomeScreen(Screen[None]):
    """The landing screen with the hero globe, target input, and menu."""

    BINDINGS = [
        Binding("ctrl+o", "open_picker", "Browse"),
        Binding("d", "run_demo", "Demo"),
        Binding("h", "open_history", "History"),
        Binding("question_mark", "help", "Help"),
        Binding("q", "quit_app", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="home-body"):
            with Horizontal(id="home-hero"):
                with Vertical(id="home-left"):
                    yield BannerWidget(id="home-banner")
                    yield Static("", id="home-tagline")
                    yield Input(
                        placeholder=_INPUT_PLACEHOLDER,
                        validators=TargetValidator(),
                        id="target",
                    )
                    yield Static("", id="target-hint")
                    yield OptionList(
                        Option("Scan a folder or Git URL  \u23ce", id=_MENU_SCAN),
                        Option("Browse folders\u2026  ^O", id=_MENU_BROWSE),
                        Option("Run the demo project  d", id=_MENU_DEMO),
                        Option("Recent scans  h", id=_MENU_RECENT),
                        Option("Help  ?", id=_MENU_HELP),
                        Option("Quit  q", id=_MENU_QUIT),
                        id="home-menu",
                    )
                    yield Static("", id="home-recent")
                with Vertical(id="home-right"):
                    yield ArtView("globe", id="home-globe")
        yield Footer()

    def on_mount(self) -> None:
        from ecdat import __version__
        from ecdat.ui.banner import SUBLINE, TAGLINE

        self._render_tagline(TAGLINE, SUBLINE, __version__)
        self._apply_layout(self.size.width, self.size.height)

        target_input = self.query_one("#target", Input)
        if self.app.initial_target:
            target_input.value = self.app.initial_target

        self._render_recents()

    def _render_tagline(self, tagline: str, subline: str, version: str) -> None:
        text = Text()
        text.append(tagline, style="bold")
        text.append("\n")
        text.append(subline, style="dim")
        text.append(f"\nv{version}", style="dim")
        self.query_one("#home-tagline", Static).update(text)

    # -- layout -----------------------------------------------------------

    def on_resize(self, event) -> None:
        self._apply_layout(event.size.width, event.size.height)

    def _apply_layout(self, width: int, height: int) -> None:
        compact = width < _NARROW_COLS or height < _NARROW_ROWS
        globe = self.query_one("#home-globe", ArtView)
        right = self.query_one("#home-right", Vertical)

        if compact:
            self.add_class("-compact")
            globe.display = False
        else:
            self.remove_class("-compact")
            globe.display = True
            if width < _WIDE_COLS or height < _WIDE_ROWS:
                right.styles.width = 24
            else:
                right.styles.width = 40

    # -- recents ----------------------------------------------------------

    def _render_recents(self) -> None:
        from ecdat.services.history import load_history

        panel = self.query_one("#home-recent", Static)
        try:
            records = load_history()[:3]
        except Exception:  # noqa: BLE001 - recents are decorative
            records = []

        self._recents = list(records)

        if not records:
            panel.update("")
            return

        lines = Text()
        lines.append("Recent scans\n", style="bold")
        for record in records:
            counts = _risk_counts(record)
            line = Text()
            line.append("\u25cf ", style="bold")
            line.append(strip_control_chars(record.target))
            line.append(f" \u2014 {counts['total']} findings")
            line.append(f" ({counts['critical']} critical)")
            lines.append(line)
            lines.append("\n")
        lines.append("Esc / click to open a scan", style="dim")
        panel.update(lines)

    def on_click(self, event) -> None:  # noqa: ANN001 - Textual event
        """Open the clicked recent scan when the recents panel is clicked."""
        if getattr(event.widget, "id", None) != "home-recent":
            return
        record = self._recent_at_offset(getattr(event, "y", 0))
        if record is not None:
            self.app.open_history_entry(record.scan_id)

    def _recent_at_offset(self, offset: int):
        """Map a click offset inside the recents panel to a record, or ``None``.

        The first line is the "Recent scans" heading, and the hint line sits at
        the bottom, so record *i* lives on line ``i + 1``.
        """
        index = offset - 1
        if 0 <= index < len(getattr(self, "_recents", [])):
            return self._recents[index]
        return None

    # -- input ------------------------------------------------------------

    def on_input_changed(self, event: Input.Changed) -> None:
        self._update_hint(event.value, event.validation_result)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        result = event.validation_result
        if result is None or not result.is_valid:
            self._update_hint(event.value, result)
            return
        self.app.start_scan(event.value)

    def _update_hint(self, value: str, result: Optional[ValidationResult]) -> None:
        hint = self.query_one("#target-hint", Static)
        if not value.strip():
            hint.update("")
            return

        try:
            target = classify_target(value)
        except ScanError as exc:
            hint.update(Text(strip_control_chars(exc.user_message), style="red"))
            return

        if result is not None and not result.is_valid:
            hint.update(
                Text(
                    strip_control_chars(result.failure_descriptions[0]),
                    style="red",
                )
            )
            return

        label = "local folder" if target.kind == "local" else "Git repository (https)"
        text = Text()
        text.append("\u2713 ", style="green")
        text.append(label)
        hint.update(text)

    # -- actions ----------------------------------------------------------

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        handler = {
            _MENU_SCAN: self._submit_target,
            _MENU_BROWSE: self.action_open_picker,
            _MENU_DEMO: self.action_run_demo,
            _MENU_RECENT: self.action_open_history,
            _MENU_HELP: self.action_help,
            _MENU_QUIT: self.action_quit_app,
        }.get(event.option_id)
        if handler is not None:
            handler()

    def _submit_target(self) -> None:
        value = self.query_one("#target", Input).value
        try:
            classify_target(value)
        except ScanError as exc:
            self.query_one("#target-hint", Static).update(
                Text(strip_control_chars(exc.user_message), style="red")
            )
            return
        self.app.start_scan(value)

    def action_open_picker(self) -> None:
        """Open the directory picker and put the result into the input."""
        self.app.push_screen(PickDirScreen(Path.cwd()), self._picker_result)

    def _picker_result(self, path: Optional[Path]) -> None:
        if path is None:
            return
        self.query_one("#target", Input).value = str(path)

    def action_run_demo(self) -> None:
        self.app.run_demo()

    def action_open_history(self) -> None:
        self.app.open_history_entry("latest")

    def action_help(self) -> None:
        self.app.action_show_help()

    def action_quit_app(self) -> None:
        self.app.exit()


def _risk_counts(record) -> dict:
    """Return ``{"total": int, "critical": int}`` for a history record."""
    total = 0
    critical = 0
    for assessment in getattr(record, "risk_assessments", []) or []:
        total += 1
        if getattr(assessment, "risk_level", None) == "critical":
            critical += 1
    return {"total": total, "critical": critical}


__all__ = ["HomeScreen", "TargetValidator"]
