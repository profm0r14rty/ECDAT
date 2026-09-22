"""The export modal — choose formats and write the result bundle.

Opened with ``e`` on the Results screen (and from the command palette).  The
dialog offers the four payload formats ECDAT can write today — CycloneDX
CBOM JSON, summary JSON, a Markdown report, and a standalone HTML report —
all preselected, plus an output-folder input.  Selecting *Export* writes the
bundle on a worker thread so the UI never blocks.

If the output folder cannot be written the dialog reports the error and stays
open; it never crashes the app.

The default output folder is derived from the scan's history id (or a UTC
timestamp when there is none) and always lives under the current working
directory.  All dynamic strings — the folder path, the written paths — enter
widgets only as :class:`rich.text.Text`.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import List, Optional, Tuple

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, SelectionList, Static
from textual.widgets.selection_list import Selection

from ecdat.services import exporters
from ecdat.services.scanner import ScanOutcome

# Widget ids.
_DIR_ID = "export-dir"
_FORMATS_ID = "export-formats"
_EXPORT_ID = "export-go"
_CANCEL_ID = "export-cancel"
_ERROR_ID = "export-error"

# (format key, human label) in display order.  SARIF is appended only when the
# exporter implements it — this branch has no ``to_sarif``, so it is omitted.
_BASE_FORMATS: Tuple[Tuple[str, str], ...] = (
    ("cbom", "CycloneDX CBOM JSON  (cbom.json)"),
    ("summary", "Summary JSON  (summary.json)"),
    ("markdown", "Markdown report  (report.md)"),
    ("html", "HTML report  (report.html)"),
)


def _available_formats() -> List[Tuple[str, str]]:
    """Return the export formats this build can actually write.

    SARIF is offered only when :func:`ecdat.services.exporters.to_sarif`
    exists, so the dialog never advertises a format the service cannot
    produce.
    """
    formats = list(_BASE_FORMATS)
    if hasattr(exporters, "to_sarif"):
        formats.append(("sarif", "SARIF 2.1.0  (results.sarif)"))
    return formats


def default_export_dir(outcome: ScanOutcome, base: Optional[Path] = None) -> Path:
    """Return the default output folder for *outcome*.

    Args:
        outcome: The scan whose bundle is being exported.
        base: Directory to place the report folder under; defaults to the
            current working directory.

    Returns:
        ``<base>/ecdat-report-<scan id or UTC timestamp>`` (not created).
    """
    base = base if base is not None else Path.cwd()
    stem = outcome.record_id or time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    return base / f"ecdat-report-{stem}"


class ExportScreen(ModalScreen[Optional[List[Path]]]):
    """Modal that writes the scan result bundle and returns the written paths.

    Dismisses with the list of written paths on success, or ``None`` when the
    user cancels.

    Args:
        outcome: The scan result to export.
        base_dir: Directory the default output folder is placed under.
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(
        self,
        outcome: ScanOutcome,
        *,
        base_dir: Optional[Path] = None,
    ) -> None:
        super().__init__()
        self.outcome = outcome
        self.formats: List[Tuple[str, str]] = _available_formats()
        self._default_dir = default_export_dir(outcome, base_dir)

    # -- composition --------------------------------------------------------

    def compose(self) -> ComposeResult:
        with Vertical(id="export-body", classes="panel"):
            yield Label("Export results", id="export-title")
            yield Static(
                Text(
                    "Choose the files to write. Everything is generated "
                    "offline — no network, no telemetry."
                ),
                id="export-note",
            )
            yield SelectionList[str](
                *[
                    Selection(label, key, True)
                    for key, label in self.formats
                ],
                id=_FORMATS_ID,
            )
            yield Label("Output folder", id="export-dir-label")
            yield Input(value=str(self._default_dir), id=_DIR_ID)
            yield Static("", id=_ERROR_ID)
            with Horizontal(id="export-buttons"):
                yield Button("Export", id=_EXPORT_ID, variant="primary")
                yield Button("Cancel", id=_CANCEL_ID)

    def on_mount(self) -> None:
        """Hide the error line until something actually fails."""
        self.query_one(f"#{_ERROR_ID}", Static).display = False

    # -- public helpers (used by tests) -------------------------------------

    def selected_formats(self) -> List[str]:
        """Return the format keys currently selected, in display order."""
        selected = self.query_one(f"#{_FORMATS_ID}", SelectionList).selected
        return [key for key, _label in self.formats if key in selected]

    # -- actions ------------------------------------------------------------

    def action_cancel(self) -> None:
        """Dismiss without exporting."""
        self.dismiss(None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == _CANCEL_ID:
            self.action_cancel()
        elif event.button.id == _EXPORT_ID:
            self._start_export()

    # -- export -------------------------------------------------------------

    def _start_export(self) -> None:
        """Validate the folder, then run the write on a worker thread."""
        formats = self.selected_formats()
        if not formats:
            self._show_error("Select at least one format to export.")
            return

        raw_dir = self.query_one(f"#{_DIR_ID}", Input).value.strip()
        if not raw_dir:
            self._show_error("Enter an output folder.")
            return

        out_dir = Path(raw_dir).expanduser()
        self.query_one(f"#{_EXPORT_ID}", Button).disabled = True
        self._hide_error()
        self._write_bundle(out_dir, formats)

    @work(thread=True, exclusive=True)
    def _write_bundle(self, out_dir: Path, formats: List[str]) -> None:
        """Write the bundle off the event loop, then report back.

        Runs on a worker thread: *every* UI touch goes through
        :meth:`~textual.app.App.call_from_thread`.
        """
        try:
            written = exporters.write_bundle(
                self.outcome.result, self.outcome.vm, out_dir, formats
            )
        except OSError as exc:
            self.app.call_from_thread(self._export_failed, str(exc))
            return
        except Exception as exc:  # noqa: BLE001 - never crash the app
            self.app.call_from_thread(
                self._export_failed, f"{type(exc).__name__}: {exc}"
            )
            return
        self.app.call_from_thread(self._export_succeeded, written)

    def _export_succeeded(self, written: List[Path]) -> None:
        """Dismiss with the written paths (main thread)."""
        self.dismiss(list(written))

    def _export_failed(self, message: str) -> None:
        """Re-enable the button and show the error, without dismissing."""
        button = self.query_one(f"#{_EXPORT_ID}", Button)
        button.disabled = False
        self._show_error(f"Export failed: {message}")

    def _show_error(self, message: str) -> None:
        """Render an error line; the dialog stays open."""
        widget = self.query_one(f"#{_ERROR_ID}", Static)
        widget.update(Text(message, style="bold red"))
        widget.display = True

    def _hide_error(self) -> None:
        """Clear and hide the error line."""
        widget = self.query_one(f"#{_ERROR_ID}", Static)
        widget.update("")
        widget.display = False


__all__ = ["ExportScreen", "default_export_dir"]
