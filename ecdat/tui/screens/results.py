"""Results screen — Overview, Findings, Recommendations, and Files tabs.

Overview shows an emblem, risk headline, stats, an animated risk chart, and the
priority-actions list.  The Findings tab is a master/detail view with live
severity / search / sort filtering, the Recommendations tab groups findings by
their PQC replacement, and the Files tab is a findings-annotated file tree.

Selecting an action in the Overview, or a file in the Files tree, jumps to the
Findings tab with the matching filter applied.
"""

from __future__ import annotations

import time
from typing import Optional

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Grid, Horizontal, Vertical, VerticalScroll
from textual.css.query import NoMatches
from textual.screen import Screen
from textual.widgets import Footer, Static, TabbedContent, TabPane

from ecdat.services.scanner import ScanOutcome
from ecdat.services.settings import load_settings
from ecdat.tui.widgets.file_tree import FileTreePane
from ecdat.tui.widgets.findings_table import FindingsPane
from ecdat.tui.widgets.header import SafeHeader
from ecdat.tui.widgets.priority_list import PriorityList
from ecdat.tui.widgets.recommendations import RecommendationsPane
from ecdat.tui.widgets.risk_chart import RiskChart
from ecdat.tui.widgets.stat_card import StatCard
from ecdat.ui import art_static, motion
from ecdat.ui.theme import PALETTE, strip_control_chars

JumpToFindings = PriorityList.JumpToFindings
FileSelected = FileTreePane.FileSelected

_HEADLINE_REVEAL_S = 0.6
_HEADLINE_TICK_S = 1.0 / 30.0


class ResultsScreen(Screen[None]):
    """The post-scan results screen.

    Tabs: Overview (emblem, headline, stats, risk donut, priority actions),
    Findings (master/detail with filters), Recommendations (grouped PQC
    replacements), and Files (findings-annotated tree).
    """

    BINDINGS = [
        Binding("1", "switch_tab('1')", "Overview"),
        Binding("2", "switch_tab('2')", "Findings"),
        Binding("3", "switch_tab('3')", "Recommendations"),
        Binding("4", "switch_tab('4')", "Files"),
        Binding("n", "new_scan", "New Scan"),
        Binding("e", "export_result", "Export"),
        Binding("escape", "back_home", "Home"),
    ]

    def __init__(self, outcome: ScanOutcome) -> None:
        super().__init__()
        self.outcome = outcome
        self.vm = outcome.vm

    # -- composition --------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield SafeHeader()
        with TabbedContent(id="results-tabs", initial="tab-overview"):
            with TabPane("Overview", id="tab-overview"):
                with VerticalScroll(id="overview-body"):
                    with Horizontal(id="result-top"):
                        yield Static("", id="result-emblem")
                        with Vertical(id="result-right"):
                            yield Static("", id="result-headline")
                            yield Static("", id="result-meta")
                    with Grid(id="stats-grid"):
                        yield StatCard("Files", self.vm.files_scanned, level="files", id="stat-files")
                        yield StatCard("Artefacts", self.vm.total, level="artefacts", id="stat-artefacts")
                        yield StatCard("Critical", self.vm.counts.get("critical", 0), level="critical", id="stat-critical")
                        yield StatCard("High", self.vm.counts.get("high", 0), level="high", id="stat-high")
                        yield StatCard("Medium", self.vm.counts.get("medium", 0), level="medium", id="stat-medium")
                        yield StatCard("Low", self.vm.counts.get("low", 0), level="low", id="stat-low")
                        yield StatCard("Quantum-safe", self.vm.counts.get("quantum-safe", 0), level="safe", id="stat-safe")
                    yield RiskChart(
                        self.vm.counts,
                        self.vm.total,
                        readiness=self.vm.safe_ratio,
                        id="risk-chart",
                    )
                    yield Static("", id="results-empty")
                    yield PriorityList(
                        self.vm.priority_actions, limit=8, id="priority-list"
                    )
            with TabPane("Findings", id="tab-findings"):
                yield FindingsPane(self.vm, id="findings-pane")
            with TabPane("Recommendations", id="tab-recommendations"):
                yield RecommendationsPane(self.vm, id="recs-pane")
            with TabPane("Files", id="tab-files"):
                yield FileTreePane(self.vm, id="file-tree-pane")
        yield Footer()

    def on_mount(self) -> None:
        self._render_emblem()
        self._render_meta()
        self.query_one("#results-empty", Static).display = self.vm.total == 0

        if self.vm.total == 0:
            self._render_empty_state()

        if self._animations:
            self._headline_frame = 0
            self._headline_started = time.monotonic()
            self._headline_timer = self.set_interval(
                _HEADLINE_TICK_S, self._tick_headline
            )
        else:
            self._render_headline_final()

    def on_unmount(self) -> None:
        """Stop the headline timer so nothing outlives the screen."""
        timer = getattr(self, "_headline_timer", None)
        if timer is not None:
            timer.stop()
            self._headline_timer = None

    # -- helpers ------------------------------------------------------------

    @property
    def _animations(self) -> bool:
        return motion.animations_enabled(load_settings().reduce_motion)

    def _render_emblem(self) -> None:
        v = art_static.verdict(self.vm.counts)
        rows = art_static.emblem_for(v)
        color = {
            "crit": PALETTE.critical,
            "warn": PALETTE.medium,
        }.get(v, PALETTE.safe)
        emblem = Text("\n".join(rows), style=color)
        self.query_one("#result-emblem", Static).update(emblem)

    def _render_headline_final(self) -> None:
        headline = art_static.headline_for(self.vm.counts, self.vm.files_scanned)
        self.query_one("#result-headline", Static).update(Text(headline))

    def _tick_headline(self) -> None:
        elapsed = time.monotonic() - self._headline_started
        progress = motion.ease_out_cubic(elapsed / _HEADLINE_REVEAL_S)
        self._headline_frame += 1
        headline = art_static.headline_for(self.vm.counts, self.vm.files_scanned)
        rendered = motion.scramble(headline, progress, self._headline_frame)
        self.query_one("#result-headline", Static).update(rendered)
        if progress >= 1.0:
            if hasattr(self, "_headline_timer") and self._headline_timer is not None:
                self._headline_timer.stop()
                self._headline_timer = None

    def _render_meta(self) -> None:
        meta = Text()
        meta.append("Target: ", style="bold")
        meta.append(Text(strip_control_chars(self.vm.target)))
        meta.append("\n")
        duration = (
            f"{self.vm.duration_s:.1f}s"
            if self.vm.duration_s is not None
            else "\u2014"
        )
        meta.append(
            f"Duration: {duration}   Files scanned: {self.vm.files_scanned}",
            style=PALETTE.muted,
        )
        meta.append("\n")
        meta.append(
            f"Artefacts: {self.vm.total}   Quantum-safe: {self.vm.counts.get('quantum-safe', 0)}"
        )
        self.query_one("#result-meta", Static).update(meta)

    def _render_risk_chart(self) -> None:
        # The RiskChart widget is already composed — no additional setup needed.
        pass

    def _render_priority_list(self) -> None:
        # The PriorityList widget is already composed — no additional setup needed.
        pass

    def _render_empty_state(self) -> None:
        empty_widget = self.query_one("#results-empty", Static)
        empty_widget.display = True
        headline = art_static.headline_for(self.vm.counts, self.vm.files_scanned)
        empty_widget.update(Text(headline, style=PALETTE.muted))

    # -- message handlers ---------------------------------------------------

    def on_priority_list_jump_to_findings(self, message: JumpToFindings) -> None:
        """Handle a jump-to-findings action from the priority list."""
        message.stop()
        self.jump_to_findings(message.family, message.file_path)

    def on_file_tree_pane_file_selected(self, message: FileSelected) -> None:
        """Handle a file selection in the Files tree.

        Jumps to the Findings tab filtered to that file.  The family filter is
        left unset: a file can hold several families, and the tree row is about
        the file, so filtering by file alone shows the complete picture.
        """
        message.stop()
        self.jump_to_findings(None, message.file_path)

    def jump_to_findings(self, family: Optional[str], file_path: Optional[str]) -> None:
        """Switch to the Findings tab and apply the requested filter.

        Args:
            family: Exact algorithm family to filter by, or ``None`` to leave
                the family filter unset.
            file_path: Exact file path to filter by, or ``None``.
        """
        tabbed = self.query_one("#results-tabs", TabbedContent)
        try:
            tabbed.query_one("#tab-findings")
        except NoMatches:
            self.notify(
                "Findings tab will be available in a later update",
                title="Coming Soon",
            )
            return

        tabbed.active = "tab-findings"
        try:
            pane = self.query_one("#findings-pane", FindingsPane)
        except NoMatches:
            return
        pane.apply_filter(file=file_path, family=family)
        pane.focus_table()

    # -- actions ------------------------------------------------------------

    def action_switch_tab(self, num: str) -> None:
        """Switch to the tab mapped from *num* (``"1"``..``"4"``).

        Moving to the Findings tab focuses its table so the ``c``/``h``/``m``/
        ``l``/``s`` filters work immediately after pressing ``2``.
        """
        tab_map = {
            "1": "tab-overview",
            "2": "tab-findings",
            "3": "tab-recommendations",
            "4": "tab-files",
        }
        tab_id = tab_map.get(num)
        if tab_id is None:
            return
        tabbed = self.query_one("#results-tabs", TabbedContent)
        try:
            tabbed.query_one(f"#{tab_id}")
            tabbed.active = tab_id
        except NoMatches:
            return

        if tab_id == "tab-findings":
            try:
                self.query_one("#findings-pane", FindingsPane).focus_table()
            except NoMatches:  # pragma: no cover - defensive
                pass

    def action_new_scan(self) -> None:
        """Return to Home to start a new scan."""
        from ecdat.tui.screens.home import HomeScreen

        self.app.switch_screen(HomeScreen())

    def action_export_result(self) -> None:
        """Open the export dialog and report where the bundle landed.

        The dialog writes the bundle on a worker thread and dismisses with the
        list of written paths (or ``None`` if cancelled).
        """
        from ecdat.tui.screens.export import ExportScreen

        self.app.push_screen(ExportScreen(self.outcome), self._export_done)

    def _export_done(self, paths: Optional[list]) -> None:
        """Toast the outcome of an export once the dialog closes."""
        if not paths:
            return
        directory = paths[0].parent
        self.notify(
            Text(f"Saved {len(paths)} files to {directory}"),
            title="Exported",
        )

    def action_back_home(self) -> None:
        """Return to the Home screen."""
        from ecdat.tui.screens.home import HomeScreen

        self.app.switch_screen(HomeScreen())


__all__ = ["ResultsScreen", "JumpToFindings"]