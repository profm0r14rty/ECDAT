"""The keyboard-help overlay.

Opened with ``?`` from anywhere (the binding lives on :class:`EcdatApp`) and
closed with ``?``, ``q`` or Escape.  The panel groups the bindings by screen so
a user can find the key they need without leaving the TUI.

All content here is static and authored by ECDAT itself — no scanned-repository
string reaches this screen.
"""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Label, Static

# (section title, [(key, description), ...]) — plain data so the panel is
# trivial to keep in sync with the real bindings.
_KEY_GROUPS = (
    (
        "Global",
        (
            ("?", "Show / hide this help"),
            ("ctrl+p", "Command palette"),
            ("t", "Cycle theme (remembered)"),
            ("q", "Quit"),
        ),
    ),
    (
        "Home",
        (
            ("Enter", "Scan the typed folder or https:// Git URL"),
            ("ctrl+o", "Browse for a folder"),
            ("d", "Run the bundled demo project"),
            ("h", "Recent scans"),
        ),
    ),
    (
        "Scan",
        (
            ("Esc", "Cancel the running scan"),
            ("r", "Retry after an error"),
            ("b", "Back to Home"),
        ),
    ),
    (
        "Results",
        (
            ("1", "Overview"),
            ("2", "Findings"),
            ("3", "Recommendations"),
            ("4", "Files"),
            ("e", "Export the result bundle"),
            ("n", "New scan"),
            ("Esc", "Back to Home"),
        ),
    ),
    (
        "Findings",
        (
            ("c/h/m/l/s", "Show only Critical / High / Medium / Low / Safe"),
            ("/", "Search algorithm, file, or family"),
            ("o", "Cycle sort order"),
            ("y", "Copy the highlighted file:line"),
            ("Esc", "Clear the search"),
        ),
    ),
)

_TITLE = "ECDAT — keyboard help"


def _build_body(version: str) -> Text:
    """Build the full help body as a single :class:`rich.text.Text`."""
    body = Text()
    for index, (title, rows) in enumerate(_KEY_GROUPS):
        if index:
            body.append("\n")
        body.append(f"{title}\n", style="bold")
        for key, description in rows:
            body.append("  ")
            body.append(f"{key:<12}", style="bold cyan")
            body.append(f"{description}\n")
    body.append("\n")
    body.append(f"ECDAT {version}\n", style="bold")
    body.append(
        "Animations are auto-disabled in CI, in non-interactive terminals and "
        "under --no-anim; set ECDAT_ANIM=0 to turn them off yourself.\n",
        style="dim",
    )
    body.append("Press ? , q or Esc to close.", style="dim")
    return body


class HelpScreen(ModalScreen[None]):
    """A scrollable, dismissible keyboard-reference overlay."""

    BINDINGS = [
        Binding("question_mark", "close", "Close", show=False),
        Binding("q", "close", "Close", show=False),
        Binding("escape", "close", "Close"),
    ]

    def compose(self) -> ComposeResult:
        from ecdat import __version__

        with VerticalScroll(id="help-body", classes="panel"):
            yield Label(_TITLE, id="help-title")
            yield Static(_build_body(__version__), id="help-content")

    def action_close(self) -> None:
        """Dismiss the overlay."""
        self.dismiss(None)


__all__ = ["HelpScreen"]
