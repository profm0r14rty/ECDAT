"""Hardening tests: every renderer/serialiser handles attacker-controlled content.

Hostile payloads include Rich markup, ANSI escapes, OSC-8 terminal hyperlinks,
HTML/JS injections, Markdown table-breaking pipes, backticks, and newlines.
The contract: renderers must treat these as literal text, not as markup.
"""

from __future__ import annotations

import re
import sys
from html.parser import HTMLParser
from io import StringIO
from pathlib import Path

import pytest

from ecdat.tests.vm_factory import HOSTILE, make_hostile_outcome, make_hostile_result, make_hostile_vm

# ---------------------------------------------------------------------------
# Test 1 — Rich scan_report must not interpret hostile values as markup
# ---------------------------------------------------------------------------


def test_rich_scan_report_escapes_hostile_markup() -> None:
    """Rich ``scan_report()`` must render ``[bold red]pwn[/]`` literally.

    Uses ``Console(force_terminal=False, color_system=None)`` to write into
    a ``StringIO``.  The output must contain the literal hostile tag (not
    interpreted) and contain NO ANSI escape bytes (``\\x1b``) or BEL (``\\x07``).
    """
    # Construct a Console directly in the test (allowed in tests per convention).
    from rich.console import Console

    from ecdat.ui.render import scan_report

    buffer = StringIO()
    out = Console(file=buffer, force_terminal=False, color_system=None)
    vm = make_hostile_vm()

    report = scan_report(vm, limit=50)
    out.print(report)

    output = buffer.getvalue()

    # The literal "[bold red]pwn[/]" text must appear (was NOT interpreted).
    assert "[bold red]pwn[/]" in output, (
        "Hostile Rich markup was absorbed by the parser instead of appearing literally"
    )

    # No ANSI escape bytes.
    assert "\x1b" not in output, (
        "ANSI escape sequences escaped into output"
    )

    # No BEL (ASCII 0x07 — used in OSC-8 hyperlinks).
    assert "\x07" not in output, (
        "BEL character (\\x07) escaped into output — OSC-8 link not sanitised"
    )


# ---------------------------------------------------------------------------
# Test 2 — Markdown tables stay rectangular despite hostile content
# ---------------------------------------------------------------------------


def _unescaped_bar_count(line: str) -> int:
    """Count ``|`` that are not preceded by an odd number of ``\\``."""
    count = 0
    backslashes = 0
    for ch in line:
        if ch == "\\":
            backslashes += 1
        elif ch == "|":
            if backslashes % 2 == 0:
                count += 1
            backslashes = 0
        else:
            backslashes = 0
    return count


def test_markdown_export_tables_are_rectangular() -> None:
    """Every Markdown table data row must have the same unescaped ``|`` count as its header.

    Hostile values include ``"a|b|c"``, backticks, and newlines — the
    ``_md_escape`` function should backslash-escape internal pipes within cells
    so that the table skeleton stays rectangular.
    """
    from ecdat.services.exporters import export_markdown

    result = make_hostile_result()
    doc = export_markdown(result)
    lines = doc.splitlines()

    # Find table blocks: a header line followed by a separator line ("|---|…").
    current_header_bars: int | None = None
    in_table = False
    table_errors: list[str] = []

    for i, raw_line in enumerate(lines):
        line = raw_line.strip()

        # Detect separator lines (e.g. "|---|-------|")
        if re.match(r"^\|[-:| ]+\|", line):
            if current_header_bars is not None:
                # We already started a table with a header row — the row before
                # this separator line gave us the expected count.  This separator
                # itself should have the same count.
                sep_bars = _unescaped_bar_count(line)
                if sep_bars != current_header_bars:
                    table_errors.append(
                        f"Line {i + 1}: separator has {sep_bars} bars, "
                        f"header had {current_header_bars}"
                    )
            in_table = True
            continue

        # Header row (or data row inside a table).
        if line.startswith("|") and line.endswith("|"):
            bars = _unescaped_bar_count(line)
            if in_table and current_header_bars is not None:
                if bars != current_header_bars:
                    table_errors.append(
                        f"Line {i + 1}: row has {bars} bars, "
                        f"header had {current_header_bars}"
                    )
            elif in_table and current_header_bars is None:
                # This is the header row — set the expected count.
                current_header_bars = bars
        else:
            # Non-table line ends the current table block.
            in_table = False
            current_header_bars = None

    if table_errors:
        pytest.fail(
            "Markdown table rows have mismatched column counts "
            f"(hostile pipe chars leaked):\n" + "\n".join(table_errors)
        )


# ---------------------------------------------------------------------------
# Test 3 — HTML export contains no unescaped scripts or event handlers
# ---------------------------------------------------------------------------


def test_html_export_no_script_no_onerror() -> None:
    """HTML export must escape ``<script>`` and ``onerror=`` away entirely.

    Uses :func:`html.escape` internally, so ``<script>`` becomes ``&lt;script&gt;``
    and ``onerror=`` becomes ``onerror=`` (already safe) or is in escaped context.
    We assert the output contains NO literal ``<script`` and NO ``onerror=``.

    Also feeds the output through :class:`html.parser.HTMLParser` — a parse
    must succeed without exception.
    """
    from ecdat.services.exporters import export_html

    result = make_hostile_result()
    doc = export_html(result)

    assert "<script" not in doc, (
        "Unescaped <script tag found in HTML export — injection not prevented"
    )
    assert "onerror=" not in doc, (
        "Unescaped 'onerror=' event handler found in HTML export"
    )

    # The document must be parseable by the stdlib HTML parser.
    parser = HTMLParser()
    try:
        parser.feed(doc)
    except Exception as exc:  # noqa: BLE001 — test assertion
        pytest.fail(f"HTMLParser failed on escaped output: {exc}")


# ---------------------------------------------------------------------------
# Test 4 — SARIF: skipped (not yet implemented in this branch)
# ---------------------------------------------------------------------------


def test_sarif_export_not_implemented_yet() -> None:
    """SARIF export is not implemented in this branch (Phase 78 not done).

    When :func:`to_sarif` is added later, this test should be replaced with
    a proper hostile-content test analogous to the Markdown and HTML tests.
    """
    pytest.skip("to_sarif not implemented in this branch (Phase 78 not done)")


# ---------------------------------------------------------------------------
# Test 5 — TUI ResultsScreen with hostile content does not crash
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tui_results_screen_with_hostile_content() -> None:
    """Push a ``ResultsScreen`` with hostile findings; assert the app survives.

    Exercises all four tabs (1/2/3/4), moves the table cursor through rows,
    and asserts that the Findings DataTable cell for the algorithm
    ``"[bold red]pwn[/]"`` has ``.plain`` equal to that literal string
    (not stripped or interpreted).
    """
    from textual.widgets import DataTable

    from ecdat.tui.app import EcdatApp
    from ecdat.tui.screens.results import ResultsScreen

    # Load the helper from the same directory.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from tui_helpers import wait_until  # noqa: E402

    outcome = make_hostile_outcome()

    app = EcdatApp(show_splash=False)
    async with app.run_test(size=(140, 44)) as pilot:
        await pilot.pause()

        # Push ResultsScreen with hostile content.
        screen = ResultsScreen(outcome)
        app.push_screen(screen)
        await pilot.pause()

        # Wait for the screen to mount.
        await wait_until(
            pilot,
            lambda: isinstance(app.screen, ResultsScreen),
            timeout=5.0,
        )

        # --- Tab 1: Overview ---
        await pilot.press("1")
        await pilot.pause(0.3)

        # --- Tab 2: Findings ---
        await pilot.press("2")
        await pilot.pause(0.5)

        # Wait for the DataTable to have rows (query on the screen instance).
        await wait_until(
            pilot,
            lambda: screen.query_one("#findings", DataTable).row_count > 0,
            timeout=5.0,
        )

        table = screen.query_one("#findings", DataTable)

        # Navigate to row 0 (the most severe finding — should be critical
        # with "[bold red]pwn[/]" algorithm).
        table.move_cursor(row=0)
        await pilot.pause(0.2)

        # Walk the DataTable rows and find the algorithm cell.
        found = False
        row_count = table.row_count
        for row_idx in range(row_count):
            # Access internal DataTable data: each row has cells keyed by ColumnKey.
            row = table.ordered_rows[row_idx]
            row_data = table._data.get(row.key, {})
            for col_key, cell in row_data.items():
                cell_str = cell.plain if hasattr(cell, "plain") else str(cell)
                if "[bold red]pwn[/]" in cell_str:
                    found = True
                    break
            if found:
                break
        assert found, (
            "No DataTable cell contained the literal hostile tag '[bold red]pwn[/]'"
        )

        # Move cursor through first three rows.
        for row_idx in range(min(3, table.row_count)):
            table.move_cursor(row=row_idx)
            await pilot.pause(0.1)

        # --- Tab 3: Recommendations ---
        await pilot.press("3")
        await pilot.pause(0.3)

        # --- Tab 4: Files ---
        await pilot.press("4")
        await pilot.pause(0.3)

        # App should not have crashed throughout.
        assert isinstance(app.screen, ResultsScreen), (
            "Screen changed unexpectedly — app may have crashed"
        )


# ---------------------------------------------------------------------------
# Meta-test: every hostile value appears in the VM somewhere
# ---------------------------------------------------------------------------


def test_every_hostile_value_appears_in_vm() -> None:
    """Sanity check: all 11 hostile values appear in at least one string field.

    This ensures the factory doesn't silently omit a payload.
    """
    vm = make_hostile_vm()

    # Collect all string content from the VM and its findings.
    all_text: list[str] = [vm.target]
    for f in vm.findings:
        all_text.extend([
            f.algorithm,
            f.family,
            f.file_path,
            f.rationale,
            f.recommended,
            f.fips_reference,
            f.snippet or "",
        ])

    # Every hostile value must appear in at least one field.
    missing: list[str] = []
    for hostile in HOSTILE:
        if not any(hostile in text for text in all_text):
            missing.append(repr(hostile))

    if missing:
        pytest.fail(
            f"Hostile values not present in VM fields: {', '.join(missing)}"
        )