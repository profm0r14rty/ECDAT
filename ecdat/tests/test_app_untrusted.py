"""Hardening tests: every renderer/serialiser handles attacker-controlled content.

Hostile payloads include Rich markup, ANSI escapes, OSC-8 terminal hyperlinks,
HTML/JS injections, Markdown table-breaking pipes, backticks, and newlines.
The contract: renderers must treat these as literal text, not as markup.
"""

from __future__ import annotations

import asyncio
import re
import sys
from datetime import datetime, timezone
from html.parser import HTMLParser
from io import StringIO
from pathlib import Path

import pytest

from ecdat.tests.vm_factory import HOSTILE, make_hostile_outcome, make_hostile_result, make_hostile_vm
from ecdat.ui.theme import strip_control_chars

# ---------------------------------------------------------------------------
# Terminal-control payloads and shared assertions
# ---------------------------------------------------------------------------

# One payload per attack family.  ``esc`` starts a CSI sequence, ``osc8`` is a
# full OSC-8 hyperlink bracketed by ESC, ``osc2`` sets the terminal title,
# ``bell`` is the bare BEL byte, and ``c1`` exercises the 8-bit C1 control block
# (CSI 0x9B, NEL 0x85).
_CONTROL_PAYLOADS = (
    ("esc", "pre\x1b[31mred\x1b[0mpost"),
    ("osc8", "\x1b]8;;https://evil.example\x07click\x1b]8;;\x07"),
    ("osc2", "\x1b]2;owned title\x07"),
    ("bell", "ding\x07dong"),
    ("c1", "c1:\x9b31m\x85x"),
)

# Printable Unicode that must survive sanitisation untouched.
_UNICODE_PAYLOAD = "caf\u00e9 \U0001f600 \u2502 \u2588 \u2714"


def _assert_no_control_bytes(text: str, context: str) -> None:
    """Assert *text* carries no raw ESC, BEL, C0 control, or C1 control bytes."""
    assert "\x1b" not in text, f"raw ESC byte leaked into {context}"
    assert "\x07" not in text, f"raw BEL byte leaked into {context}"
    c0 = [c for c in text if ord(c) < 0x20 and c not in "\t\n"]
    assert not c0, f"C0 control byte(s) {[hex(ord(c)) for c in c0]} leaked into {context}"
    c1 = [c for c in text if 0x80 <= ord(c) <= 0x9F]
    assert not c1, f"C1 control byte(s) {[hex(ord(c)) for c in c1]} leaked into {context}"


def _hostile_result_with(payloads: tuple) -> object:
    """Build a :class:`ScanResult` whose every string field is hostile.

    Each payload is placed in a distinct detection/recommendation slot so all
    of them reach the renderers and exporters in one pass.
    """
    from ecdat_core.models import Detection, Recommendation, RiskAssessment, ScanResult

    detections = []
    assessments = []
    recommendations = []
    for i, (_name, payload) in enumerate(payloads):
        det_id = f"det-{i}"
        detections.append(
            Detection(
                id=det_id,
                file_path=f"src/{payload}.py",
                line_number=10 + i,
                matched_text=payload,
                asset_type="algorithm",
                algorithm_family=payload,
                key_size_bits=2048,
                quantum_vulnerable=True,
                classically_broken=False,
                confidence=0.85,
                language="python",
                detection_method="regex",
            )
        )
        assessments.append(
            RiskAssessment(
                detection_id=det_id,
                migration_time_years=3.0,
                shelf_life_years=5.0,
                threat_horizon_years=5.0,
                urgency_ratio=1.5,
                risk_level="critical",
                mosca_violation=True,
            )
        )
        recommendations.append(
            Recommendation(
                detection_id=det_id,
                recommended_algorithm=payload,
                fips_reference=payload,
                rationale=payload,
                latency_note="",
                migration_note="",
            )
        )

    return ScanResult(
        scan_id=payloads[0][1],
        target=payloads[-1][1],
        detections=detections,
        risk_assessments=assessments,
        recommendations=recommendations,
        scanned_at=datetime(2026, 9, 22, 12, 0, 0, tzinfo=timezone.utc).isoformat(),
        files_scanned=len(detections),
    )


# ---------------------------------------------------------------------------
# Test 1b — every control payload is neutralised across every surface
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name,payload", _CONTROL_PAYLOADS, ids=[p[0] for p in _CONTROL_PAYLOADS])
def test_control_payload_neutralised_in_rich_report(name: str, payload: str) -> None:
    """A raw control payload must not survive into the Rich pretty report."""
    from rich.console import Console

    from ecdat.services.viewmodel import build_scan_vm
    from ecdat.ui.render import scan_report

    result = _hostile_result_with(((name, payload),))
    vm = build_scan_vm(result, target=payload)
    buffer = StringIO()
    Console(file=buffer, force_terminal=False, color_system=None).print(
        scan_report(vm, limit=50)
    )
    _assert_no_control_bytes(buffer.getvalue(), f"rich report ({name})")


@pytest.mark.parametrize("name,payload", _CONTROL_PAYLOADS, ids=[p[0] for p in _CONTROL_PAYLOADS])
def test_control_payload_neutralised_in_markdown(name: str, payload: str) -> None:
    """A raw control payload must not survive into the Markdown export."""
    from ecdat.services.exporters import export_markdown

    doc = export_markdown(_hostile_result_with(((name, payload),)))
    _assert_no_control_bytes(doc, f"markdown export ({name})")


@pytest.mark.parametrize("name,payload", _CONTROL_PAYLOADS, ids=[p[0] for p in _CONTROL_PAYLOADS])
def test_control_payload_neutralised_in_html(name: str, payload: str) -> None:
    """A raw control payload must not survive into the HTML export."""
    from ecdat.services.exporters import export_html

    doc = export_html(_hostile_result_with(((name, payload),)))
    _assert_no_control_bytes(doc, f"html export ({name})")


def test_printable_unicode_survives_report_and_exports() -> None:
    """Accented letters, emoji, and box-drawing chars are NOT stripped."""
    from rich.console import Console

    from ecdat.services.exporters import export_html, export_markdown
    from ecdat.services.viewmodel import build_scan_vm
    from ecdat.ui.render import scan_report

    result = _hostile_result_with((("unicode", _UNICODE_PAYLOAD),))
    vm = build_scan_vm(result, target=_UNICODE_PAYLOAD)

    buffer = StringIO()
    Console(file=buffer, force_terminal=False, color_system=None).print(scan_report(vm))
    assert _UNICODE_PAYLOAD in buffer.getvalue()

    assert _UNICODE_PAYLOAD in export_markdown(result)
    assert _UNICODE_PAYLOAD in export_html(result)


def test_strip_control_chars_preserves_normal_unicode() -> None:
    """The sanitizer keeps printable Unicode and TAB/LF; drops CR and controls."""
    assert strip_control_chars(_UNICODE_PAYLOAD) == _UNICODE_PAYLOAD
    assert strip_control_chars("a\tb\nc") == "a\tb\nc"
    assert strip_control_chars("a\rb") == "ab"
    assert strip_control_chars("a\x1b[31mb\x07c\x9bd") == "a[31mbcd"


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
# Test 5b — no widget content carries raw control bytes (byte-level, headless)
# ---------------------------------------------------------------------------


def _collect_tui_text(widget) -> str:
    """Collect the plain text of every renderable in *widget*'s subtree.

    Walks all descendants and pulls each widget's rendered ``.plain`` text,
    then explicitly harvests the tabular widgets whose content is not exposed
    through ``render()``: :class:`~textual.widgets.DataTable` cells,
    :class:`~textual.widgets.Tree` labels, and
    :class:`~textual.widgets.OptionList` prompts.

    This is the same content the compositor paints to the terminal, so scanning
    it for raw control bytes is a faithful check of what a hostile repo could
    emit through the TUI.
    """
    from textual.widgets import DataTable, OptionList, Tree

    def _tree_labels(node) -> list:
        labels = []
        label = getattr(node, "label", None)
        if label is not None:
            labels.append(getattr(label, "plain", str(label)))
        for child in getattr(node, "children", []) or []:
            labels.extend(_tree_labels(child))
        return labels

    parts: list[str] = []
    for node in widget.walk_children(with_self=True):
        try:
            rendered = node.render()
        except Exception:  # noqa: BLE001 - not every node exposes a renderable
            rendered = None
        if rendered is not None:
            plain = getattr(rendered, "plain", rendered if isinstance(rendered, str) else None)
            if plain:
                parts.append(plain)

        if isinstance(node, DataTable):
            for row_idx in range(node.row_count):
                try:
                    for cell in node.get_row_at(row_idx):
                        parts.append(getattr(cell, "plain", str(cell)))
                except Exception:  # noqa: BLE001 - defensive, no row visible yet
                    pass
        if isinstance(node, Tree):
            parts.extend(_tree_labels(node.root))
        if isinstance(node, OptionList):
            for idx in range(node.option_count):
                prompt = node.get_option_at_index(idx).prompt
                parts.append(getattr(prompt, "plain", str(prompt)))

    return "\n".join(parts)


@pytest.mark.asyncio
async def test_tui_widgets_carry_no_raw_control_bytes() -> None:
    """Every Results tab must render hostile VM fields without control bytes.

    Drives the real TUI headlessly and, on each of the four tabs, harvests the
    text of every widget in the subtree.  Two properties are asserted:

    1. no raw ESC / BEL / other C0 / C1 byte is present anywhere (the escape
       family cannot reach the terminal), and
    2. the hostile payloads still appear — stripped of control bytes — so the
       test proves sanitisation, not that the content was dropped or the
       widget silently failed to render.
    """
    from ecdat.tui.app import EcdatApp
    from ecdat.tui.screens.results import ResultsScreen

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from tui_helpers import wait_until  # noqa: E402

    outcome = make_hostile_outcome()
    app = EcdatApp(show_splash=False)

    async with app.run_test(size=(140, 44)) as pilot:
        await pilot.pause()
        app.push_screen(ResultsScreen(outcome))
        await wait_until(
            pilot,
            lambda: isinstance(app.screen, ResultsScreen),
            timeout=5.0,
        )

        for key, label in (("1", "overview"), ("2", "findings"),
                           ("3", "recommendations"), ("4", "files")):
            await pilot.press(key)
            await pilot.pause(0.4)
            text = _collect_tui_text(app.screen)
            _assert_no_control_bytes(text, f"TUI {label} tab")

        # Positive control: the hostile markup content is still rendered, just
        # with its control bytes stripped.
        on_findings = _collect_tui_text(app.screen)
        payloads = [h for h in HOSTILE if strip_control_chars(h) in on_findings]
        assert payloads, "no hostile payload survived into the TUI (widgets may have failed to render)"

        assert isinstance(app.screen, ResultsScreen)


def test_tui_text_helper_has_teeth() -> None:
    """The extraction helper must actually surface a raw ESC when one exists."""
    from rich.text import Text
    from textual.app import App, ComposeResult
    from textual.widgets import Static

    class _Leaky(App):
        def compose(self) -> ComposeResult:
            yield Static(Text("leak\x1b[31mhere"))

    async def _run() -> str:
        app = _Leaky()
        async with app.run_test() as pilot:
            await pilot.pause()
            return _collect_tui_text(app.screen)

    text = asyncio.run(_run())
    assert "\x1b" in text, "helper failed to see a raw ESC byte — test would be vacuous"


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