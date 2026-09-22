"""The scan-history screen — browse and reopen past scans.

A :class:`~textual.widgets.DataTable` lists every saved scan newest-first
(When · Target · Files · Findings · Critical · High).  Enter reopens the
highlighted scan on the Results screen, ``d`` deletes it after a confirmation
dialog, and Escape returns to the previous screen.

Corrupt history entries are skipped silently by
:mod:`ecdat.services.history` — this screen only ever sees valid records, and
shows a friendly empty state when there are none.

Targets come from scanned repositories and are therefore attacker-controlled:
every one enters the table only as :class:`rich.text.Text`.
"""

from __future__ import annotations

from typing import List, Optional

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen, Screen
from textual.widgets import Button, DataTable, Footer, Header, Label, Static

from ecdat.services.history import HistoryError, delete_scan, list_scans
from ecdat.services.scanner import ScanOutcome
from ecdat.services.viewmodel import build_scan_vm
from ecdat_core.models import ScanResult

# Widget ids.
_TABLE_ID = "history-table"
_EMPTY_ID = "history-empty"

_CONFIRM_YES = "history-confirm-yes"
_CONFIRM_NO = "history-confirm-no"


def _risk_counts(record: ScanResult) -> dict:
    """Return ``{"total", "critical", "high"}`` counts for *record*."""
    total = len(record.detections)
    critical = 0
    high = 0
    for assessment in record.risk_assessments:
        level = getattr(assessment, "risk_level", None)
        if level == "critical":
            critical += 1
        elif level == "high":
            high += 1
    return {"total": total, "critical": critical, "high": high}


def _when(record: ScanResult) -> str:
    """Return a compact ``YYYY-MM-DD HH:MM`` label from ``scanned_at``."""
    stamp = getattr(record, "scanned_at", "") or ""
    # ISO 8601 — "2026-01-01T12:00:00+00:00" → "2026-01-01 12:00".
    return stamp[:16].replace("T", " ")


class _ConfirmDeleteScreen(ModalScreen[bool]):
    """A yes/no confirmation dialog for deleting a history entry."""

    BINDINGS = [
        Binding("escape", "no", "Cancel"),
        Binding("y", "yes", "Delete"),
    ]

    def __init__(self, target: str) -> None:
        super().__init__()
        self._target = target

    def compose(self) -> ComposeResult:
        with Vertical(id="history-confirm", classes="panel"):
            yield Label("Delete this scan?", id="history-confirm-title")
            yield Static(Text(self._target), id="history-confirm-target")
            with Horizontal(id="history-confirm-buttons"):
                yield Button("Delete", id=_CONFIRM_YES, variant="error")
                yield Button("Cancel", id=_CONFIRM_NO)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == _CONFIRM_YES)

    def action_yes(self) -> None:
        """Confirm deletion."""
        self.dismiss(True)

    def action_no(self) -> None:
        """Cancel deletion."""
        self.dismiss(False)


class HistoryScreen(Screen[None]):
    """Browse past scans; Enter reopens, ``d`` deletes, Escape goes back."""

    BINDINGS = [
        Binding("escape", "back", "Back"),
        Binding("d", "delete", "Delete"),
        Binding("n", "new_scan", "New Scan"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._records: List[ScanResult] = []

    # -- composition --------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="history-body"):
            yield Static("Scan history", id="history-title")
            yield DataTable(id=_TABLE_ID, zebra_stripes=True)
            yield Static("", id=_EMPTY_ID)
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one(f"#{_TABLE_ID}", DataTable)
        table.cursor_type = "row"
        table.add_columns("When", "Target", "Files", "Findings", "Critical", "High")
        self._reload()

    # -- data ---------------------------------------------------------------

    def _reload(self) -> None:
        """Reload the history table from disk."""
        try:
            self._records = list_scans()
        except Exception:  # noqa: BLE001 - a broken store shows the empty state
            self._records = []

        table = self.query_one(f"#{_TABLE_ID}", DataTable)
        table.clear()
        for record in self._records:
            counts = _risk_counts(record)
            table.add_row(
                Text(_when(record)),
                Text(record.target),
                Text(str(record.files_scanned)),
                Text(str(counts["total"])),
                Text(str(counts["critical"])),
                Text(str(counts["high"])),
                key=record.scan_id,
            )

        empty = self.query_one(f"#{_EMPTY_ID}", Static)
        if self._records:
            empty.display = False
            empty.update("")
        else:
            empty.display = True
            empty.update(
                Text(
                    "No saved scans yet. Run a scan and it will appear here.",
                    style="dim",
                )
            )
            table.display = False

    # -- public helpers (used by tests) -------------------------------------

    def record_count(self) -> int:
        """Return the number of history records currently listed."""
        return len(self._records)

    def selected_record(self) -> Optional[ScanResult]:
        """Return the record under the cursor, or ``None`` when empty."""
        table = self.query_one(f"#{_TABLE_ID}", DataTable)
        if table.row_count == 0:
            return None
        index = table.cursor_row
        if 0 <= index < len(self._records):
            return self._records[index]
        return None

    # -- actions ------------------------------------------------------------

    def action_back(self) -> None:
        """Return to the previous screen if there is one, else Home."""
        if len(self.app.screen_stack) > 1:
            self.app.pop_screen()
            return
        from ecdat.tui.screens.home import HomeScreen

        self.app.switch_screen(HomeScreen())

    def action_new_scan(self) -> None:
        """Go back to the Home screen to start another scan."""
        from ecdat.tui.screens.home import HomeScreen

        self.app.switch_screen(HomeScreen())

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Reopen the highlighted scan on the Results screen."""
        event.stop()
        self._open_selected()

    def _open_selected(self) -> None:
        record = self.selected_record()
        if record is None:
            return
        vm = build_scan_vm(
            record,
            target=record.target,
            duration_s=None,
        )
        outcome = ScanOutcome(
            result=record,
            vm=vm,
            duration_s=0.0,
            record_id=record.scan_id,
        )
        from ecdat.tui.screens.results import ResultsScreen

        self.app.switch_screen(ResultsScreen(outcome))

    def action_delete(self) -> None:
        """Delete the highlighted record after a confirmation dialog."""
        record = self.selected_record()
        if record is None:
            return
        self.app.push_screen(
            _ConfirmDeleteScreen(record.target), self._delete_confirmed(record)
        )

    def _delete_confirmed(self, record: ScanResult):
        """Build the confirm callback for *record*."""

        def _callback(confirmed: Optional[bool]) -> None:
            if not confirmed:
                return
            try:
                delete_scan(record.scan_id)
            except HistoryError as exc:
                self.notify(Text(str(exc)), title="History", severity="error")
                return
            self._reload()

        return _callback


__all__ = ["HistoryScreen"]
