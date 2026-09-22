"""RecommendationsPane widget: table of PQC migration recommendations with file-list detail panel.

Each row groups findings by their recommended replacement algorithm, ranked
by the worst risk level in the group.  Highlighting a row updates the adjacent
detail panel with the affected files.
"""

from __future__ import annotations

from typing import List, Tuple

from rich.style import Style
from rich.text import Text
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import DataTable, Static

from ecdat.services.viewmodel import ScanVM
from ecdat.ui.render import risk_chip
from ecdat.ui.theme import PALETTE, RISK_INDEX, strip_control_chars

_NO_RECOMMENDATION = "(none)"

_EMPTY_STATE_TEXT = "All algorithms are quantum-safe \u2014 nothing to migrate."


class RecommendationsPane(Horizontal):
    """Recommendations tab: table of recommended PQC algorithms and affected files.

    Groups findings from :class:`~ecdat.services.viewmodel.ScanVM` by their
    recommended algorithm, ranks them worst-risk-first, and shows a detail
    panel listing the affected files for the highlighted row.

    Args:
        vm: The completed scan view-model.
        id: DOM id (defaults to ``"recs-pane"``).
        classes: Additional CSS classes.
    """

    def __init__(
        self,
        vm: ScanVM,
        *,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(id=id or "recs-pane", classes=classes)
        self.vm: ScanVM = vm
        """The scan view-model."""
        self._row_key_to_rec: dict[str, str] = {}
        """Mapping from DataTable row key (``rec-{idx}``) to recommendation key."""

    # ------------------------------------------------------------------
    # Composition
    # ------------------------------------------------------------------

    def compose(self):
        """Compose the table and detail panel side by side."""
        yield DataTable(id="recs-table", cursor_type="row", zebra_stripes=True)
        with VerticalScroll(id="recs-detail"):
            yield Static(id="recs-files")

    # ------------------------------------------------------------------
    # Mount — populate the table
    # ------------------------------------------------------------------

    def on_mount(self) -> None:
        """Set up columns, sort groups, and populate the DataTable."""
        table = self.query_one("#recs-table", DataTable)
        self._configure_columns(table)

        groups = self.vm.by_recommendation
        keys_to_show = list(groups.keys())

        # Filter out "(none)" when there are other recommendations.
        if _NO_RECOMMENDATION in keys_to_show and len(keys_to_show) > 1:
            keys_to_show = [k for k in keys_to_show if k != _NO_RECOMMENDATION]

        # If only "(none)" remains, check whether it has any non-quantum-safe
        # findings — if not, it is an empty state.
        if len(keys_to_show) == 1 and keys_to_show[0] == _NO_RECOMMENDATION:
            if all(
                f.risk_level == "quantum-safe" for f in groups[_NO_RECOMMENDATION]
            ):
                keys_to_show = []

        # Empty state.
        if not keys_to_show:
            self._show_empty()
            return

        # Sort: worst risk first (lowest RISK_INDEX), then count desc, then key.
        def _sort_key(rec_key: str) -> tuple[int, int, str]:
            group = groups[rec_key]
            worst_level = min(
                group,
                key=lambda f: RISK_INDEX.get(f.risk_level, 99),
            ).risk_level
            return (RISK_INDEX.get(worst_level, 99), -len(group), rec_key)

        keys_to_show.sort(key=_sort_key)

        for idx, rec_key in enumerate(keys_to_show):
            group = groups[rec_key]
            worst_level = min(
                group,
                key=lambda f: RISK_INDEX.get(f.risk_level, 99),
            ).risk_level

            # Top 3 distinct family names (sorted deterministically).
            families: list[str] = list(dict.fromkeys(f.family for f in group))
            families.sort()
            top3 = families[:3]
            replaces = ", ".join(top3)
            if len(families) > 3:
                replaces += " \u2026"  # single ellipsis character

            fips = group[0].fips_reference or "\u2014"  # em-dash when empty

            row_key = f"rec-{idx}"
            self._row_key_to_rec[row_key] = rec_key

            # All dynamic/untrusted strings wrapped in Text(…, style=Style())
            # to disable Rich markup parsing (attacker-controlled repo content).
            table.add_row(
                Text(strip_control_chars(rec_key), style=Style()),
                Text(str(len(group)), style=Style()),
                risk_chip(worst_level),
                Text(strip_control_chars(replaces), style=Style()),
                Text(strip_control_chars(fips), style=Style()),
                key=row_key,
            )

    def _configure_columns(self, table: DataTable) -> None:
        """Add the five columns to *table*."""
        table.add_column("Recommended algorithm")
        table.add_column("# artefacts")
        table.add_column("Worst risk")
        table.add_column("Replaces")
        table.add_column("FIPS")

    def _show_empty(self) -> None:
        """Populate the detail panel with the 'nothing to migrate' message."""
        msg = Text(
            _EMPTY_STATE_TEXT,
            style=Style(color=PALETTE.muted, italic=True),
        )
        self.query_one("#recs-files", Static).update(msg)

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def on_data_table_row_highlighted(
        self, event: DataTable.RowHighlighted
    ) -> None:
        """Update ``#recs-files`` with the affected files for the highlighted row."""
        row_key = event.row_key.value if event.row_key else None
        rec_key = self._row_key_to_rec.get(row_key or "")
        if rec_key is None:
            return

        files = self.affected_files(rec_key)
        static = self.query_one("#recs-files", Static)

        text = Text()
        for f in files[:20]:
            text.append(Text(strip_control_chars(f), style=Style()))
            text.append("\n")

        remaining = len(files) - 20
        if remaining > 0:
            text.append(
                Text(
                    f"+{remaining} more",
                    style=Style(color=PALETTE.muted, italic=True),
                )
            )

        static.update(text)

    # ------------------------------------------------------------------
    # Public query helpers (used by tests and parent screens)
    # ------------------------------------------------------------------

    def recommendation_rows(self) -> List[Tuple[str, int, str]]:
        """Return ``(recommended_algorithm, count, worst_risk)`` for every group.

        Returns:
            A list of tuples, one per distinct recommendation key in the
            view-model.
        """
        rows: List[Tuple[str, int, str]] = []
        for rec_key, group in self.vm.by_recommendation.items():
            worst = min(
                group,
                key=lambda f: RISK_INDEX.get(f.risk_level, 99),
            ).risk_level
            rows.append((rec_key, len(group), worst))
        return rows

    def affected_files(self, rec: str) -> List[str]:
        """Return deduplicated ``"path:line"`` strings for *rec*.

        Args:
            rec: A recommendation key in ``vm.by_recommendation``.

        Returns:
            Deduplicated file paths with line numbers, preserving
            first-seen order.
        """
        group = self.vm.by_recommendation.get(rec, [])
        seen: set[tuple[str, int]] = set()
        result: List[str] = []
        for f in group:
            key = (f.file_path, f.line)
            if key not in seen:
                seen.add(key)
                result.append(f"{f.file_path}:{f.line}")
        return result


__all__ = ["RecommendationsPane"]