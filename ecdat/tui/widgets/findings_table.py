"""FindingsPane widget: the Findings tab's master/detail view.

Layout (top to bottom):

- a control bar of five severity toggle chips (Critical / High / Medium / Low /
  Safe — all active by default), a search :class:`~textual.widgets.Input`, and
  a "Showing N of M" label;
- a split of a :class:`~textual.widgets.DataTable` of findings against a
  :class:`~ecdat.tui.widgets.finding_detail.FindingDetail` pane.  The split is
  horizontal at ≥110 columns and stacks vertically below that (``-narrow``).

Interaction: ``c`` / ``h`` / ``m`` / ``l`` / ``s`` toggle the matching chip
while the pane is focused, ``/`` focuses the search box, ``Esc`` clears it and
refocuses the table, ``o`` cycles the sort mode, and clicking a column header
sorts by that column.

Every cell is a :class:`rich.text.Text` — the findings carry attacker-controlled
file paths, algorithm names and snippets, so none of them may be interpolated
into a Rich markup string.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from rich.style import Style
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import DataTable, Input, Static

from ecdat.services.filtering import SORT_LABELS, SORT_MODES, filter_findings, sort_findings
from ecdat.services.viewmodel import FindingVM, ScanVM
from ecdat.tui.widgets.finding_detail import FindingDetail
from ecdat.ui.render import risk_chip
from ecdat.ui.theme import PALETTE, RISK_COLORS

# Severity levels in display order, paired with the chip key that toggles them.
_LEVELS: tuple[tuple[str, str], ...] = (
    ("critical", "c"),
    ("high", "h"),
    ("medium", "m"),
    ("low", "l"),
    ("quantum-safe", "s"),
)

_LEVEL_LABELS: Dict[str, str] = {
    "critical": "Critical",
    "high": "High",
    "medium": "Medium",
    "low": "Low",
    "quantum-safe": "Safe",
}

# The width below which the master/detail split stacks vertically.
_NARROW_COLUMNS = 110

# Column index → sort mode, for header clicks.
_HEADER_SORT: Dict[int, str] = {
    0: "risk",
    1: "algorithm",
    2: "algorithm",
    3: "file",
    4: "urgency",
    5: "risk",
}


def _ellipsis_location(path: str, line: int, width: int = 46) -> str:
    """Ellipsise ``path:line`` in the middle, keeping the filename and line."""
    suffix = f":{line}"
    full = f"{path}{suffix}"
    if len(full) <= width:
        return full

    parts = path.split("/")
    if len(parts) <= 2:
        return full[: width - 1] + "\u2026"

    right = "/".join(parts[-2:]) + suffix
    left_budget = width - len(right) - 1
    if left_budget < 3:
        return f"\u2026{right}"[:width]

    left = parts[0]
    i = 1
    while i < len(parts) - 2 and len(left) + 1 + len(parts[i]) <= left_budget:
        left = f"{left}/{parts[i]}"
        i += 1
    return f"{left}\u2026/{right}"


class FindingsPane(Vertical):
    """Master/detail findings view with live severity, search and sort filters.

    Args:
        vm: The scan view-model whose findings are displayed.
        id: DOM id.
        classes: Additional CSS classes.
    """

    BINDINGS = [
        Binding("c", "toggle_level('critical')", "Critical", show=False),
        Binding("h", "toggle_level('high')", "High", show=False),
        Binding("m", "toggle_level('medium')", "Medium", show=False),
        Binding("l", "toggle_level('low')", "Low", show=False),
        Binding("s", "toggle_level('quantum-safe')", "Safe", show=False),
        Binding("slash", "focus_search", "Search", show=False),
        Binding("o", "cycle_sort", "Sort", show=False),
        Binding("y", "copy_location", "Copy path", show=False),
        Binding("escape", "clear_search", "", show=False),
    ]

    def __init__(
        self,
        vm: ScanVM,
        *,
        id: Optional[str] = None,
        classes: Optional[str] = None,
    ) -> None:
        cls = f"{classes} findings-pane" if classes else "findings-pane"
        super().__init__(id=id, classes=cls)
        self.vm = vm

        self._active: set[str] = {level for level, _key in _LEVELS}
        self._query = ""
        self._file_filter: Optional[str] = None
        self._family_filter: Optional[str] = None
        self._sort_mode = SORT_MODES[0]
        self._visible: List[FindingVM] = []
        self._suppress_highlight = False

    # -- composition --------------------------------------------------------

    def compose(self) -> ComposeResult:
        """Compose the control bar and the master/detail split."""
        with Horizontal(id="findings-controls"):
            for level, key in _LEVELS:
                yield Static("", id=f"chip-{level}", classes="chip")
            yield Input(placeholder="Search algorithm, file, family\u2026", id="findings-search")
            yield Static("", id="findings-showing")
        with Horizontal(id="findings-split"):
            yield DataTable(id="findings", zebra_stripes=True)
            yield FindingDetail(id="finding-detail")

    def on_mount(self) -> None:
        """Configure the table, render the chips, and populate the rows."""
        table = self.query_one("#findings", DataTable)
        table.cursor_type = "row"
        table.add_columns("Risk", "Algorithm", "Family", "Location", "Conf %", "Flags")
        for level, _key in _LEVELS:
            self._render_chip(level)
        self._repopulate()
        self._apply_layout(self.size.width)

    # -- public accessors (used by the screen and tests) --------------------

    @property
    def sort_mode(self) -> str:
        """The active sort mode."""
        return self._sort_mode

    def active_levels(self) -> List[str]:
        """Return the active severity levels, in display order."""
        return [level for level, _key in _LEVELS if level in self._active]

    def visible_findings(self) -> List[FindingVM]:
        """Return the findings currently shown in the table (post filter+sort)."""
        return list(self._visible)

    def showing_label(self) -> str:
        """Return the current "Showing N of M" text."""
        return f"Showing {len(self._visible)} of {self.vm.total}"

    def selected_finding(self) -> Optional[FindingVM]:
        """Return the finding under the cursor, or ``None`` when the table is empty."""
        table = self.query_one("#findings", DataTable)
        if table.row_count == 0:
            return None
        index = table.cursor_row
        if 0 <= index < len(self._visible):
            return self._visible[index]
        return None

    # -- filtering ----------------------------------------------------------

    def apply_filter(
        self,
        file: Optional[str] = None,
        family: Optional[str] = None,
    ) -> None:
        """Set the exact file/family filters and refresh the table.

        Called by the screen when the Overview's priority list or the Files
        tree asks to jump to a specific finding.  Passing ``None`` clears that
        filter.

        Args:
            file: Exact file path to restrict to, or ``None``.
            family: Exact algorithm family to restrict to, or ``None``.
        """
        self._file_filter = file
        self._family_filter = family
        self._repopulate()

    def focus_table(self) -> None:
        """Move focus onto the findings table (used after a tab switch)."""
        try:
            self.query_one("#findings", DataTable).focus()
        except Exception:  # noqa: BLE001 - before mount
            pass

    def _repopulate(self) -> None:
        """Re-run filter + sort and rebuild the table rows."""
        filtered = filter_findings(
            self.vm.findings,
            levels=self._active,
            query=self._query,
            file=self._file_filter,
            family=self._family_filter,
        )
        self._visible = sort_findings(filtered, self._sort_mode)

        table = self.query_one("#findings", DataTable)
        previous = self._current_id()
        self._suppress_highlight = True
        try:
            table.clear()
            for finding in self._visible:
                table.add_row(*self._row_cells(finding), key=finding.id)
        finally:
            self._suppress_highlight = False

        self._restore_cursor(previous)
        self.query_one("#findings-showing", Static).update(
            Text(self.showing_label(), style=Style(color=PALETTE.muted))
        )
        self._update_detail()

    def _row_cells(self, f: FindingVM) -> tuple:
        """Build the six Text cells for one finding."""
        flags = []
        if f.quantum_vulnerable:
            flags.append("Q")
        if f.classically_broken:
            flags.append("!")
        return (
            risk_chip(f.risk_level),
            Text(f.algorithm),
            Text(f.family),
            Text(_ellipsis_location(f.file_path, f.line)),
            Text(f"{f.confidence * 100:.0f}%"),
            Text(" ".join(flags) if flags else "\u2014"),
        )

    def _current_id(self) -> Optional[str]:
        """Return the id of the currently highlighted finding, if any."""
        finding = self.selected_finding()
        return finding.id if finding is not None else None

    def _restore_cursor(self, finding_id: Optional[str]) -> None:
        """Keep the cursor on *finding_id* when it survived the refilter."""
        table = self.query_one("#findings", DataTable)
        if table.row_count == 0 or finding_id is None:
            return
        for index, finding in enumerate(self._visible):
            if finding.id == finding_id:
                table.move_cursor(row=index)
                return

    def _update_detail(self) -> None:
        """Push the highlighted finding into the detail pane."""
        detail = self.query_one("#finding-detail", FindingDetail)
        detail.show_finding(self.selected_finding())

    # -- chips --------------------------------------------------------------

    def _render_chip(self, level: str) -> None:
        """Render one severity chip in its active/inactive state.

        Active chips carry their risk colour and a filled dot; inactive chips
        dim to muted with a hollow dot.  The label text is static but still
        built with :class:`~rich.text.Text` for consistency with the rest of
        the widget.
        """
        active = level in self._active
        chip = Text()
        if active:
            chip.append("\u25cf ", style=Style(color=RISK_COLORS.get(level, PALETTE.text), bold=True))
            chip.append(_LEVEL_LABELS[level], style=Style(color=RISK_COLORS.get(level, PALETTE.text), bold=True))
        else:
            chip.append("\u25cb ", style=Style(color=PALETTE.muted, dim=True))
            chip.append(_LEVEL_LABELS[level], style=Style(color=PALETTE.muted, dim=True))
        try:
            self.query_one(f"#chip-{level}", Static).update(chip)
        except Exception:  # noqa: BLE001 - during mount
            pass

    def _solo_level(self, level: str) -> None:
        """Focus the severity filter on *level* (``c``/``h``/``m``/``l``/``s``).

        Pressing a severity key narrows the table to that single level, matching
        the playbook's ``2 → c`` acceptance check ("pressing ``c`` … restricts
        rows to critical only").  Pressing the key again while it is already the
        sole active level restores all five — otherwise there would be no
        keyboard way back to the full list.
        """
        if self._active == {level}:
            self._active = {lvl for lvl, _key in _LEVELS}
        else:
            self._active = {level}
        for lvl, _key in _LEVELS:
            self._render_chip(lvl)
        self._repopulate()

    def _toggle_level(self, level: str) -> None:
        """Flip one severity level on/off (multi-select, used by chip clicks)."""
        if level in self._active:
            self._active.discard(level)
        else:
            self._active.add(level)
        self._render_chip(level)
        self._repopulate()

    # -- events -------------------------------------------------------------

    def on_input_changed(self, event: Input.Changed) -> None:
        """Re-filter as the user types in the search box."""
        if event.input.id != "findings-search":
            return
        self._query = event.value
        self._repopulate()

    def on_click(self, event) -> None:  # noqa: ANN001 - Textual event
        """Toggle a severity chip when it is clicked."""
        widget_id = getattr(event.widget, "id", None)
        if not isinstance(widget_id, str) or not widget_id.startswith("chip-"):
            return
        level = widget_id[len("chip-"):]
        if level in {lvl for lvl, _k in _LEVELS}:
            self._toggle_level(level)

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """Update the detail pane whenever the cursor moves to another row."""
        if self._suppress_highlight:
            return
        self._update_detail()

    def on_data_table_header_selected(self, event: DataTable.HeaderSelected) -> None:
        """Sort by the clicked column."""
        mode = _HEADER_SORT.get(event.column_index)
        if mode is not None:
            self._sort_mode = mode
            self._repopulate()

    def on_resize(self, event) -> None:  # noqa: ANN001 - Textual event
        """Stack the split when the terminal is narrow."""
        self._apply_layout(event.size.width)

    def _apply_layout(self, width: int) -> None:
        """Toggle ``-narrow`` on the split based on *width*."""
        split = self.query_one("#findings-split", Horizontal)
        if width < _NARROW_COLUMNS:
            split.add_class("-narrow")
        else:
            split.remove_class("-narrow")

    # -- actions ------------------------------------------------------------

    def action_toggle_level(self, level: str) -> None:
        """Severity keys solo that level; chip clicks toggle it (see handlers)."""
        self._solo_level(level)

    def action_focus_search(self) -> None:
        """Focus the search box (``/``)."""
        try:
            self.query_one("#findings-search", Input).focus()
        except Exception:  # noqa: BLE001
            pass

    def action_clear_search(self) -> None:
        """Clear the search text and refocus the table (``Esc``).

        ``Esc`` on the Results screen means "back to Home".  To keep that
        meaning available from inside this pane, ``Esc`` only clears here when
        the search box is focused or a query is active; otherwise it delegates
        to the screen's own ``Esc`` handler.
        """
        try:
            search = self.query_one("#findings-search", Input)
        except Exception:  # noqa: BLE001 - before mount
            return

        if not search.has_focus and not self._query:
            back_home = getattr(self.screen, "action_back_home", None)
            if callable(back_home):
                back_home()
            return

        search.value = ""
        self._query = ""
        self._repopulate()
        self.focus_table()

    def action_cycle_sort(self) -> None:
        """Cycle to the next sort mode (``o``)."""
        try:
            index = SORT_MODES.index(self._sort_mode)
        except ValueError:
            index = -1
        self._sort_mode = SORT_MODES[(index + 1) % len(SORT_MODES)]
        self._repopulate()
        self.notify(
            f"Sorted by {SORT_LABELS.get(self._sort_mode, self._sort_mode)}",
            title="Findings",
        )

    def action_copy_location(self) -> None:
        """Copy ``file:line`` for the highlighted finding (``y``)."""
        finding = self.selected_finding()
        if finding is None:
            return
        location = f"{finding.file_path}:{finding.line}"
        copier = getattr(self.app, "copy_to_clipboard", None)
        if callable(copier):
            copier(location)
            self.notify(Text(f"Copied {location}"), title="Findings")
        else:  # pragma: no cover - headless fallback
            self.notify(Text(location), title="Findings")


__all__ = ["FindingsPane"]
