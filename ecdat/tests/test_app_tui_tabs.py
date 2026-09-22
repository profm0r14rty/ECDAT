"""Pilot tests for the Recommendations and Files tabs (Phase 86).

Both panes are driven by the showcase fixture's view-model: 70 findings, 9
distinct recommendation keys, 8 files across 7 top-level folders.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from rich.text import Text
from textual.widgets import DataTable, Static, TabbedContent

from ecdat.services.scanner import ScanOutcome, classify_target, perform_scan
from ecdat.services.viewmodel import build_scan_vm
from ecdat.tui.app import EcdatApp
from ecdat.tui.screens.results import ResultsScreen
from ecdat.tui.widgets.file_tree import FileTreePane
from ecdat.tui.widgets.findings_table import FindingsPane
from ecdat.tui.widgets.recommendations import RecommendationsPane
from ecdat.ui.theme import strip_control_chars
from ecdat_core.models import Detection, Recommendation, RiskAssessment, ScanResult

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tui_helpers import wait_until  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
SHOWCASE_REPO = REPO_ROOT / "ecdat_core" / "tests" / "fixtures" / "showcase_repo"

EXPECTED_TOP_LEVEL = [
    "auth",
    "certs",
    "keyexchange",
    "legacy",
    "payments",
    "quantum",
    "tokens",
]

HOSTILE = "[bold red]evil\x1b[31m[/]"
HOSTILE_DIR = "[bold red]evil\x1b[31m"


def _outcome() -> ScanOutcome:
    return perform_scan(classify_target(str(SHOWCASE_REPO)), label="showcase")


def _plain(widget) -> str:
    rendered = widget.render()
    return getattr(rendered, "plain", str(rendered))


def _empty_outcome() -> ScanOutcome:
    result = ScanResult(
        scan_id="empty",
        target="empty",
        detections=[],
        risk_assessments=[],
        recommendations=[],
        scanned_at=datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat(),
        files_scanned=0,
    )
    return ScanOutcome(
        result=result, vm=build_scan_vm(result, target="empty"), duration_s=0.0
    )


def _hostile_outcome() -> ScanOutcome:
    """A scan whose directory and file names are markup-shaped and hostile.

    Two files live under two different top-level directories so the common
    prefix is empty and the hostile directory names survive into the tree.
    """
    detections = [
        Detection(
            id="h1",
            file_path=f"{HOSTILE_DIR}/payload.py",
            line_number=1,
            matched_text="crypto",
            asset_type="algorithm",
            algorithm_family="RSA",
            key_size_bits=1024,
            quantum_vulnerable=True,
            classically_broken=False,
            confidence=0.9,
            language="python",
            detection_method="regex",
        ),
        Detection(
            id="h2",
            file_path=f"nested/{HOSTILE_DIR}/deep.py",
            line_number=3,
            matched_text="crypto",
            asset_type="algorithm",
            algorithm_family=HOSTILE,
            key_size_bits=None,
            quantum_vulnerable=True,
            classically_broken=False,
            confidence=0.5,
            language="python",
            detection_method="regex",
        ),
    ]
    result = ScanResult(
        scan_id="hostile",
        target=HOSTILE,
        detections=detections,
        risk_assessments=[
            RiskAssessment(
                detection_id="h1",
                migration_time_years=1.0,
                shelf_life_years=2.0,
                threat_horizon_years=5.0,
                urgency_ratio=0.6,
                risk_level="medium",
                mosca_violation=False,
            ),
            RiskAssessment(
                detection_id="h2",
                migration_time_years=1.0,
                shelf_life_years=2.0,
                threat_horizon_years=5.0,
                urgency_ratio=0.6,
                risk_level="medium",
                mosca_violation=False,
            ),
        ],
        recommendations=[
            Recommendation(
                detection_id="h1",
                recommended_algorithm=HOSTILE,
                fips_reference=HOSTILE,
                rationale="because",
                latency_note="",
                migration_note="",
            ),
            Recommendation(
                detection_id="h2",
                recommended_algorithm=HOSTILE,
                fips_reference=HOSTILE,
                rationale="because",
                latency_note="",
                migration_note="",
            ),
        ],
        scanned_at=datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat(),
        files_scanned=2,
    )
    return ScanOutcome(
        result=result, vm=build_scan_vm(result, target=HOSTILE), duration_s=0.1
    )


async def _open_tab(pilot, app, key: str, tab_id: str):
    """Press *key* and wait for *tab_id* to become active, then return the screen."""
    tabs = app.screen.query_one("#results-tabs", TabbedContent)
    await pilot.press(key)
    await wait_until(pilot, lambda: tabs.active == tab_id, timeout=10.0)
    await pilot.pause()
    return app.screen


# ---------------------------------------------------------------------------
# Recommendations tab
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recommendations_tab_exists() -> None:
    outcome = _outcome()
    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(140, 44)) as pilot:
        await pilot.pause()
        app.push_screen(ResultsScreen(outcome))
        await pilot.pause()
        screen = await _open_tab(pilot, app, "3", "tab-recommendations")
        pane = screen.query_one("#recs-pane", RecommendationsPane)
        assert pane.query_one("#recs-table", DataTable) is not None
        assert pane.query_one("#recs-files", Static) is not None


@pytest.mark.asyncio
async def test_one_table_row_per_distinct_recommendation() -> None:
    outcome = _outcome()
    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(140, 44)) as pilot:
        await pilot.pause()
        app.push_screen(ResultsScreen(outcome))
        await pilot.pause()
        screen = await _open_tab(pilot, app, "3", "tab-recommendations")
        pane = screen.query_one("#recs-pane", RecommendationsPane)
        table = pane.query_one("#recs-table", DataTable)

        rows = pane.recommendation_rows()
        expected_keys = {
            key for key in outcome.vm.by_recommendation if key != "(none)"
        }
        assert {row[0] for row in rows} == set(outcome.vm.by_recommendation)
        assert table.row_count == len(expected_keys)


@pytest.mark.asyncio
async def test_recommendations_row_label_matches_a_key() -> None:
    outcome = _outcome()
    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(140, 44)) as pilot:
        await pilot.pause()
        app.push_screen(ResultsScreen(outcome))
        await pilot.pause()
        screen = await _open_tab(pilot, app, "3", "tab-recommendations")
        pane = screen.query_one("#recs-pane", RecommendationsPane)
        table = pane.query_one("#recs-table", DataTable)

        row_keys = set(outcome.vm.by_recommendation)
        first_cell = table.get_row_at(0)[0]
        assert getattr(first_cell, "plain", str(first_cell)) in row_keys


_CHIP_SEVERITY = {
    "CRITICAL": 0,
    "HIGH": 1,
    "MEDIUM": 2,
    "LOW": 3,
    "SAFE": 4,
}


@pytest.mark.asyncio
async def test_recommendations_worst_risk_is_chip() -> None:
    outcome = _outcome()
    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(140, 44)) as pilot:
        await pilot.pause()
        app.push_screen(ResultsScreen(outcome))
        await pilot.pause()
        screen = await _open_tab(pilot, app, "3", "tab-recommendations")
        pane = screen.query_one("#recs-pane", RecommendationsPane)
        table = pane.query_one("#recs-table", DataTable)

        risk_order = ["critical", "high", "medium", "low", "quantum-safe"]
        for index in range(table.row_count):
            row = table.get_row_at(index)
            rec_key = getattr(row[0], "plain", str(row[0]))
            chip_label = getattr(row[2], "plain", str(row[2]))
            group_worst = min(
                (f.risk_level for f in outcome.vm.by_recommendation[rec_key]),
                key=risk_order.index,
            )
            assert _CHIP_SEVERITY[chip_label] == risk_order.index(group_worst)


@pytest.mark.asyncio
async def test_recommendation_highlight_lists_affected_files() -> None:
    outcome = _outcome()
    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(140, 44)) as pilot:
        await pilot.pause()
        app.push_screen(ResultsScreen(outcome))
        await pilot.pause()
        screen = await _open_tab(pilot, app, "3", "tab-recommendations")
        pane = screen.query_one("#recs-pane", RecommendationsPane)
        table = pane.query_one("#recs-table", DataTable)

        table.move_cursor(row=0)
        await pilot.pause()
        rec = table.get_row_at(0)[0]
        rec_key = getattr(rec, "plain", str(rec))
        files = pane.affected_files(rec_key)
        assert files
        shown = _plain(pane.query_one("#recs-files", Static))
        assert files[0] in shown


@pytest.mark.asyncio
async def test_affected_files_are_deduplicated() -> None:
    outcome = _outcome()
    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(140, 44)) as pilot:
        await pilot.pause()
        app.push_screen(ResultsScreen(outcome))
        await pilot.pause()
        screen = await _open_tab(pilot, app, "3", "tab-recommendations")
        pane = screen.query_one("#recs-pane", RecommendationsPane)

        for rec in outcome.vm.by_recommendation:
            files = pane.affected_files(rec)
            assert len(files) == len(set(files))


@pytest.mark.asyncio
async def test_recommendations_empty_state() -> None:
    outcome = _empty_outcome()
    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.push_screen(ResultsScreen(outcome))
        await pilot.pause()
        screen = await _open_tab(pilot, app, "3", "tab-recommendations")
        pane = screen.query_one("#recs-pane", RecommendationsPane)
        table = pane.query_one("#recs-table", DataTable)
        assert table.row_count == 0
        assert "quantum-safe" in _plain(pane.query_one("#recs-files", Static))


# ---------------------------------------------------------------------------
# Files tab
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_files_tab_exists() -> None:
    outcome = _outcome()
    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(140, 44)) as pilot:
        await pilot.pause()
        app.push_screen(ResultsScreen(outcome))
        await pilot.pause()
        screen = await _open_tab(pilot, app, "4", "tab-files")
        assert screen.query_one("#file-tree-pane", FileTreePane) is not None


@pytest.mark.asyncio
async def test_tree_has_a_node_per_top_level_folder() -> None:
    outcome = _outcome()
    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(140, 44)) as pilot:
        await pilot.pause()
        app.push_screen(ResultsScreen(outcome))
        await pilot.pause()
        screen = await _open_tab(pilot, app, "4", "tab-files")
        tree = screen.query_one("#file-tree-pane", FileTreePane)
        assert tree.top_level_names() == EXPECTED_TOP_LEVEL


@pytest.mark.asyncio
async def test_tree_has_a_node_per_file() -> None:
    outcome = _outcome()
    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(140, 44)) as pilot:
        await pilot.pause()
        app.push_screen(ResultsScreen(outcome))
        await pilot.pause()
        screen = await _open_tab(pilot, app, "4", "tab-files")
        tree = screen.query_one("#file-tree-pane", FileTreePane)
        assert len(tree.file_nodes()) == len(outcome.vm.by_file)


@pytest.mark.asyncio
async def test_selecting_a_file_jumps_to_findings_with_filter() -> None:
    outcome = _outcome()
    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(140, 44)) as pilot:
        await pilot.pause()
        screen = ResultsScreen(outcome)
        app.push_screen(screen)
        await pilot.pause()
        await _open_tab(pilot, app, "4", "tab-files")
        tree = screen.query_one("#file-tree-pane", FileTreePane)

        # Find the auth directory and select its file node.
        target_path = next(
            path for _name, path in tree.file_nodes() if "/auth/" in path
        )
        auth_dir = next(
            node for node in tree.root.children if node.label.plain.startswith("auth")
        )
        file_node = auth_dir.children[0]
        tree.select_node(file_node)
        await pilot.pause()

        tabs = screen.query_one("#results-tabs", TabbedContent)
        assert tabs.active == "tab-findings"
        pane = screen.query_one("#findings-pane", FindingsPane)
        visible = pane.visible_findings()
        assert visible
        assert all(f.file_path == target_path for f in visible)


@pytest.mark.asyncio
async def test_file_selected_message_carries_payload() -> None:
    message = FileTreePane.FileSelected("/repo/auth/login.py", "RSA")
    assert message.file_path == "/repo/auth/login.py"
    assert message.family == "RSA"


@pytest.mark.asyncio
async def test_directory_counts_aggregate_children() -> None:
    outcome = _outcome()
    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(140, 44)) as pilot:
        await pilot.pause()
        app.push_screen(ResultsScreen(outcome))
        await pilot.pause()
        screen = await _open_tab(pilot, app, "4", "tab-files")
        tree = screen.query_one("#file-tree-pane", FileTreePane)

        # legacy/ holds 7 MD5 + 1 3DES = 8 findings in the showcase repo.
        legacy = next(
            node for node in tree.root.children if node.label.plain.startswith("legacy")
        )
        assert "(8)" in legacy.label.plain


# ---------------------------------------------------------------------------
# Hostile content
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hostile_directory_names_render_literally() -> None:
    outcome = _hostile_outcome()
    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.push_screen(ResultsScreen(outcome))
        await pilot.pause()
        screen = await _open_tab(pilot, app, "4", "tab-files")
        tree = screen.query_one("#file-tree-pane", FileTreePane)

        labels = [node.label.plain for node in tree.root.children]
        # Markup-shaped names survive literally, but the raw ESC byte is stripped
        # at the untrusted-content boundary.
        assert any(strip_control_chars(HOSTILE_DIR) in label for label in labels)
        assert strip_control_chars(HOSTILE) in tree.root.label.plain
        assert "\x1b" not in tree.root.label.plain


@pytest.mark.asyncio
async def test_hostile_recommendation_renders_literally() -> None:
    outcome = _hostile_outcome()
    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.push_screen(ResultsScreen(outcome))
        await pilot.pause()
        screen = await _open_tab(pilot, app, "3", "tab-recommendations")
        pane = screen.query_one("#recs-pane", RecommendationsPane)

        shown = _plain(pane.query_one("#recs-files", Static))
        assert shown  # something rendered without raising
        table = pane.query_one("#recs-table", DataTable)
        cells = table.get_row_at(0)
        joined = "".join(getattr(c, "plain", str(c)) for c in cells)
        assert strip_control_chars(HOSTILE) in joined
        assert "\x1b" not in joined
