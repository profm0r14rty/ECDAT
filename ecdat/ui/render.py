"""Rich report renderers for ECDAT scan results, plus the Mosca timeline.

Every report renderer consumes :class:`~ecdat.services.viewmodel.ScanVM` and
:class:`~ecdat.services.viewmodel.FindingVM` — never raw engine models.
ALL dynamic values (file paths, snippets, algorithm names, rationales) are
wrapped in :class:`rich.text.Text` — they are NEVER interpolated into Rich
markup strings because they come from attacker-controlled scanned repos.

The Mosca timeline is deliberately split into two layers:

- :func:`mosca_timeline_segments` — a **pure** function returning plain
  ``(text, style_token)`` cells.  No Rich objects, no console, no colour
  lookup: it is trivially unit-testable and reusable by a Textual widget.
- :func:`mosca_timeline` — a thin Rich wrapper that maps style tokens to the
  :mod:`ecdat.ui.theme` palette and returns a printable
  :class:`rich.console.Group`.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.style import Style
from rich.table import Table
from rich.text import Text

from ecdat.services.viewmodel import FindingVM, ScanVM
from ecdat.ui.art_static import emblem_for, headline_for, verdict
from ecdat.ui.theme import (
    MINT_GRADIENT,
    PALETTE,
    RISK_COLORS,
    RISK_LABELS,
    RISK_ORDER,
    strip_control_chars,
)

# ---------------------------------------------------------------------------
# Character sets
# ---------------------------------------------------------------------------

_UNICODE_EIGHTHS = "\u258f\u258e\u258d\u258c\u258b\u258a\u2589\u2588"  # ▏▎▍▌▋▊▉█
"""Eighth-block characters, index 0 = 1/8, index 7 = 8/8 (full block)."""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe(value: str) -> Text:
    """Wrap a string in a plain :class:`~rich.text.Text` — no markup parsing.

    The value is first passed through
    :func:`~ecdat.ui.theme.strip_control_chars` so a raw ESC / C0 / C1 byte in
    an attacker-controlled field can never reach the terminal as part of an
    ANSI/OSC/DCS escape sequence.
    """
    return Text(strip_control_chars(value), style=Style())


def _ellipsis_path(path: str, line: int | None, width: int = 50) -> str:
    """Ellipsise a file path in the middle, preserving the filename.

    ``"very/long/path/to/some/file.py:123"`` →
    ``"very/lo…/some/file.py:123"`` (or similar).
    """
    suffix = f":{line}" if line is not None else ""
    full = f"{path}{suffix}"
    if len(full) <= width:
        return full

    # Keep filename + preceding segment on the right, prefix on the left.
    parts = path.split("/")
    if len(parts) <= 2:
        # Can't really ellipsise — truncate right.
        return full[: width - 1] + "\u2026"

    # Keep last 2 segments on the right.
    right = "/".join(parts[-2:]) + suffix
    left_budget = width - len(right) - 1  # -1 for the ellipsis sigil
    if left_budget < 3:
        return f"\u2026{right}"[:width]

    left = parts[0]
    i = 1
    while i < len(parts) - 2 and len(left) + 1 + len(parts[i]) <= left_budget:
        left = f"{left}/{parts[i]}"
        i += 1

    return f"{left}\u2026/{right}"


def _flag_text(finding: FindingVM) -> str:
    """Return flag letters for a finding: ``Q`` = quantum-vulnerable, ``!`` = classically broken."""
    flags = []
    if finding.quantum_vulnerable:
        flags.append("Q")
    if finding.classically_broken:
        flags.append("!")
    return " ".join(flags) if flags else "\u2014"


# ---------------------------------------------------------------------------
# Public renderers
# ---------------------------------------------------------------------------


def smooth_bar(
    fraction: float,
    width: int,
    *,
    unicode: bool = True,
) -> Text:
    """Render a horizontal progress bar with eighth-block precision.

    Args:
        fraction: Fill ratio, clamped to ``[0, 1]``.
        width: Total bar width in cells.
        unicode: Use Unicode eighth-blocks (``True``) or ASCII ``#``/``-``.

    Returns:
        A :class:`~rich.text.Text` of exactly *width* cells.
    """
    fraction = max(0.0, min(1.0, fraction))
    width = max(1, width)

    filled = fraction * width
    full_cells = int(filled)
    frac_part = filled - full_cells

    result = Text()
    accent_style = Style(color=PALETTE.accent)
    muted_style = Style(color=PALETTE.muted)

    for i in range(width):
        if i < full_cells:
            if unicode:
                result.append("\u2588", style=accent_style)  # full block
            else:
                result.append("#", style=accent_style)
        elif i == full_cells and frac_part > 0:
            eig_idx = min(7, int(frac_part * 8))
            if unicode and eig_idx > 0:
                result.append(_UNICODE_EIGHTHS[eig_idx - 1], style=accent_style)
            elif unicode:
                result.append(" ", style=muted_style)
            else:
                result.append("-", style=muted_style)
        else:
            if unicode:
                result.append(" ", style=muted_style)
            else:
                result.append("-", style=muted_style)

    return result


def risk_chip(level: str) -> Text:
    """Return a short coloured label for *level* (e.g. ``"CRITICAL"``).

    Uses :data:`~ecdat.ui.theme.RISK_COLORS` and
    :data:`~ecdat.ui.theme.RISK_LABELS`.
    """
    color = RISK_COLORS.get(level, PALETTE.text)
    label = RISK_LABELS.get(level, level.upper())
    return Text(label, style=Style(color=color, bold=True))


def summary_panel(vm: ScanVM) -> Panel:
    """Render the scan summary panel with padlock emblem and headline."""
    v = verdict(vm.counts)
    emblem = emblem_for(v)
    headline = headline_for(vm.counts, vm.files_scanned)

    # Compute safe percentage.
    safe_pct = round(vm.safe_ratio * 100)

    # Build the right-side content.
    right = Text()
    hl = _safe(headline)
    hl.stylize(Style(bold=True))
    right.append(hl)
    right.append("\n\n")

    # Target.
    right.append("Target  ", style=Style(color=PALETTE.muted))
    right.append(_safe(vm.target))
    right.append("\n")

    # Duration.
    dur = f"{vm.duration_s:.1f}s" if vm.duration_s is not None else "N/A"
    right.append("Duration ", style=Style(color=PALETTE.muted))
    right.append(_safe(dur))
    right.append("\n")

    # Files scanned.
    right.append("Files    ", style=Style(color=PALETTE.muted))
    right.append(_safe(str(vm.files_scanned)))
    right.append("\n")

    # Quantum-safe percentage.
    right.append("Safe     ", style=Style(color=PALETTE.muted))
    right.append(f"{safe_pct}%", style=Style(color=PALETTE.safe, bold=True))

    # Build the emblem as left-side content.
    left_text = Text()
    for i, row in enumerate(emblem):
        if i > 0:
            left_text.append("\n")
        # Colour the emblem.
        color = {"crit": PALETTE.critical, "warn": PALETTE.high}.get(
            v, PALETTE.safe
        )
        left_text.append(row, style=Style(color=color, bold=True))

    # Build layout with columns.
    content = Table.grid(padding=(0, 2))
    content.add_column(justify="left", vertical="top")
    content.add_column(justify="left", vertical="top")
    content.add_row(left_text, right)

    return Panel(
        content,
        title="Scan Summary",
        title_align="left",
        border_style=PALETTE.border,
        padding=(1, 2),
    )


def risk_bars(vm: ScanVM) -> RenderableType:
    """Render a horizontal stacked risk-distribution bar.

    Each risk level gets a segment proportional to its count.  Returns a
    :class:`~rich.table.Table` showing a stacked bar and a legend row.
    """
    total = vm.total
    grid = Table.grid(padding=(0, 1))
    grid.add_column(justify="left")

    # Stacked bar row.
    if total == 0:
        bar_text = Text(" " * 40, style=Style(color=PALETTE.muted, bgcolor=PALETTE.surface))
        grid.add_row(bar_text)
    else:
        bar = Text()
        for level in RISK_ORDER:
            count = vm.counts.get(level, 0)
            if count == 0:
                continue
            seg_width = max(1, round(count / total * 40))
            color = RISK_COLORS.get(level, PALETTE.muted)
            bar.append("\u2588" * seg_width, style=Style(color=color, bgcolor=color))
        # Pad to exactly 40 cells.
        current = len(bar.plain)
        if current < 40:
            bar.append(" " * (40 - current))
        grid.add_row(bar)

    # Legend row.
    legend_parts: list[Text] = []
    for level in RISK_ORDER:
        count = vm.counts.get(level, 0)
        color = RISK_COLORS.get(level, PALETTE.muted)
        label = RISK_LABELS.get(level, level)
        part = Text(f" {label}:{count} ", style=Style(color=color))
        legend_parts.append(part)

    legend_row = Text()
    for i, part in enumerate(legend_parts):
        if i > 0:
            legend_row.append(" ")
        legend_row.append(part)
    grid.add_row(legend_row)

    return grid


def findings_table(vm: ScanVM, *, limit: int = 15) -> Table:
    """Render the findings table.

    Columns: Risk, Algorithm, Location (file:line ellipsised), Conf %, Flags.
    Shows at most *limit* rows; a ``"+N more"`` row is appended when truncated.

    Args:
        vm: The scan view-model.
        limit: Maximum findings to display.

    Returns:
        A :class:`~rich.table.Table`.
    """
    table = Table(
        title="Findings",
        title_style=f"bold {PALETTE.accent}",
        border_style=PALETTE.border,
        header_style=Style(color=PALETTE.muted, bold=True),
        expand=False,
        pad_edge=True,
    )
    table.add_column("Risk", style="bold", no_wrap=True)
    table.add_column("Algorithm", no_wrap=True)
    table.add_column("Location", no_wrap=True)
    table.add_column("Conf %", justify="right", no_wrap=True)
    table.add_column("Flags", no_wrap=True)

    displayed = vm.findings[:limit]
    for f in displayed:
        loc = _ellipsis_path(f.file_path, f.line)
        conf = f"{f.confidence * 100:.0f}%"
        flags = _flag_text(f)

        # Risk chip.
        risk_cell = risk_chip(f.risk_level)

        table.add_row(
            risk_cell,
            _safe(f.algorithm),
            _safe(loc),
            _safe(conf),
            _safe(flags),
        )

    # "+N more" row if truncated.
    remaining = len(vm.findings) - limit
    if remaining > 0:
        more = Text(f"+{remaining} more", style=Style(color=PALETTE.muted, italic=True))
        table.add_row(more, Text(), Text(), Text(), Text())

    return table


def priority_actions_panel(vm: ScanVM, *, limit: int = 8) -> Panel:
    """Render the priority-actions panel.

    Groups findings by ``(family, file_path)``, ranked worst-first.  Shows at
    most *limit* rows.

    Args:
        vm: The scan view-model.
        limit: Maximum priority actions to display.

    Returns:
        A :class:`~rich.panel.Panel`.
    """
    actions = vm.priority_actions[:limit]

    table = Table(
        border_style=PALETTE.border,
        header_style=Style(color=PALETTE.muted, bold=True),
        expand=False,
        pad_edge=False,
    )
    table.add_column("Risk", no_wrap=True)
    table.add_column("Family", no_wrap=True)
    table.add_column("File", no_wrap=False)
    table.add_column("#", justify="right", no_wrap=True)
    table.add_column("Recommend", no_wrap=True)

    for pa in actions:
        loc = _ellipsis_path(pa.file_path, None, width=40)
        table.add_row(
            risk_chip(pa.worst_risk),
            _safe(pa.family),
            _safe(loc),
            _safe(str(pa.count)),
            _safe(pa.recommended),
        )

    if not actions:
        table.add_row(
            Text("No priority actions", style=Style(color=PALETTE.safe, italic=True)),
            Text(), Text(), Text(), Text(),
        )

    return Panel(
        table,
        title="Priority Actions",
        title_align="left",
        border_style=PALETTE.border,
        padding=(0, 1),
    )


def recommendations_table(vm: ScanVM) -> Table:
    """Render the recommendations table (algorithm → PQC replacement).

    Returns:
        A :class:`~rich.table.Table`.
    """
    table = Table(
        title="Recommendations",
        title_style=f"bold {PALETTE.accent}",
        border_style=PALETTE.border,
        header_style=Style(color=PALETTE.muted, bold=True),
        expand=False,
        pad_edge=True,
    )
    table.add_column("Algorithm")
    table.add_column("Count", justify="right")
    table.add_column("Recommendation")

    for rec_name, findings in sorted(vm.by_recommendation.items()):
        if rec_name == "(none)":
            continue
        # Gather unique families that have this recommendation.
        families = sorted({f.family for f in findings})
        table.add_row(
            _safe(", ".join(families)),
            _safe(str(len(findings))),
            _safe(rec_name),
        )

    if not table.rows:
        table.add_row(
            Text("All algorithms are quantum-safe", style=Style(color=PALETTE.safe, italic=True)),
            Text(),
            Text(),
        )

    return table


def legend() -> Panel:
    """Render a legend panel explaining flags, risk levels, and colours.

    Returns:
        A :class:`~rich.panel.Panel`.
    """
    content = Text()
    content.append("Flags ", style=Style(bold=True))
    content.append("Q = quantum-vulnerable   ")
    content.append("! = classically broken\n", style=Style(color=PALETTE.critical))
    content.append("Risk levels: ", style=Style(bold=True))
    for level in RISK_ORDER:
        chip = risk_chip(level)
        content.append(chip)
        content.append("  ")

    return Panel(
        content,
        title="Legend",
        title_align="left",
        border_style=PALETTE.border,
        padding=(1, 2),
    )


def scan_report(
    vm: ScanVM,
    *,
    limit: int = 15,
    unicode: bool = True,
) -> Group:
    """Render the complete scan report as a :class:`~rich.console.Group`.

    When the scan found no cryptographic artefacts (:attr:`ScanVM.total` == 0),
    a single friendly panel is returned instead of the full layout.

    Args:
        vm: The scan view-model.
        limit: Maximum findings to display in the table.
        unicode: Use Unicode characters (``True``) or ASCII fallback.

    Returns:
        A :class:`~rich.console.Group` ready for ``console.print()``.
    """
    # Empty scan — special case.
    if vm.total == 0:
        no_results = Text(
            f"No cryptographic artefacts detected in {vm.files_scanned} files",
            style=Style(color=PALETTE.safe),
        )
        no_results.justify = "center"
        return Group(
            Panel(
                no_results,
                border_style=PALETTE.border,
                padding=(2, 4),
            )
        )

    elements: List[RenderableType] = [
        summary_panel(vm),
        Text(),  # spacer
        risk_bars(vm),
        Text(),  # spacer
        findings_table(vm, limit=limit),
    ]

    # Priority actions — only if there are non-quantum-safe findings.
    if vm.priority_actions:
        elements.append(Text())  # spacer
        elements.append(priority_actions_panel(vm))

    elements.append(Text())  # spacer
    elements.append(recommendations_table(vm))
    elements.append(Text())  # spacer
    elements.append(legend())

    return Group(*elements)


# ---------------------------------------------------------------------------
# Mosca timeline
# ---------------------------------------------------------------------------

# A timeline row is a list of ``(text, style_token)`` segments.
Segment = Tuple[str, str]
Row = List[Segment]

# Prefix rendered on the first two rows, before the bars.  ``"NOW ├"`` is
# exactly 5 cells wide (``├`` is a single box-drawing cell).
_NOW_PREFIX = "NOW \u251c"
_PREFIX_WIDTH = len(_NOW_PREFIX)

# Row 4 label — the legend spelling out what each bar means.
_LABEL = "X data lifetime \u00b7 Y migration \u00b7 Z quantum arrival"

# Exposed-window fill character (medium shade), tokenised as "gap".
_GAP_CHAR = "\u2592"


def _cells(value: float, scale: float) -> int:
    """Return the number of cells for *value* at *scale*.

    Every non-zero value gets at least one cell (an invisible bar is worse than
    an approximate one); zero maps to zero.  A non-positive *scale* (only
    possible for degenerate widths) still yields one cell for a non-zero value.
    """
    if value <= 0:
        return 0
    if scale <= 0:
        return 1
    return max(1, int(round(value * scale)))


def _fit(segments: Row, width: int) -> Row:
    """Pad or truncate *segments* so the row is exactly *width* cells wide.

    Padding is emitted as a single ``("plain")`` segment.  If the content
    already exceeds *width*, later segments are truncated (dropping any
    remainder) so the exact-width invariant always holds.
    """
    budget = width
    out: Row = []
    for text, token in segments:
        if not text:
            continue
        if budget <= 0:
            break
        if len(text) <= budget:
            out.append((text, token))
            budget -= len(text)
        else:
            out.append((text[:budget], token))
            budget = 0
            break
    if budget > 0:
        out.append((" " * budget, "plain"))
    return out


def mosca_timeline_segments(x: float, y: float, z: float, width: int) -> List[Row]:
    """Build the raw cell rows for a Mosca-inequality timeline.

    The timeline visualises ``X + Y`` (the time we must stay safe) against
    ``Z`` (the quantum arrival horizon):

    - **row 1** — ``"NOW ├"`` followed by the X bar (token ``"x"``) and the Y
      bar (token ``"y"``), i.e. ``X + Y`` laid out on the same axis as Z.
    - **row 2** — ``"NOW ├"`` followed by the Z bar (token ``"z"``).
    - **row 3** — present **only** when ``X + Y > Z`` (a Mosca violation):
      spaces up to Z, then ``"▒"`` (token ``"gap"``) marking the exposed
      window from Z to ``X + Y``.
    - **row 4** — the legend label (token ``"label"``).

    Scaling uses ``scale = (width - 6) / (max(X + Y, Z) * 1.05)``, leaving a
    small headroom so the longest bar never touches the right edge.  Every row
    is returned with **exactly** *width* cells (padded with a ``"plain"``
    segment when short).

    Args:
        x: Data-lifetime component (years), the "X" bar.
        y: Migration-time component (years), the "Y" bar.
        z: Quantum threat horizon (years), the "Z" bar.
        width: Total number of terminal cells per row.

    Returns:
        A list of rows, each a list of ``(text, style_token)`` segments whose
        combined text length equals *width*.  Tokens used: ``x``, ``y``, ``z``,
        ``gap``, ``label``, ``plain``.
    """
    width = max(0, int(width))
    total = x + y
    max_value = max(total, z)

    # Scale in cells-per-year.  Guard against a zero/negative denominator.
    scale = ((width - 6) / (max_value * 1.05)) if max_value > 0 else 0.0

    x_cells = _cells(x, scale)
    y_cells = _cells(y, scale)
    z_cells = _cells(z, scale)
    sum_cells = x_cells + y_cells

    rows: List[Row] = []

    rows.append(
        _fit(
            [
                (_NOW_PREFIX, "label"),
                ("#" * x_cells, "x"),
                ("#" * y_cells, "y"),
            ],
            width,
        )
    )
    rows.append(
        _fit(
            [
                (_NOW_PREFIX, "label"),
                ("#" * z_cells, "z"),
            ],
            width,
        )
    )

    if total > z:
        gap_cells = sum_cells - z_cells
        if gap_cells < 1:
            # Rounding could collapse a genuine (but tiny) violation to zero
            # cells; keep the violation visible with a single-cell marker.
            gap_cells = 1
        rows.append(
            _fit(
                [
                    (" " * _PREFIX_WIDTH, "plain"),
                    (" " * z_cells, "plain"),
                    (_GAP_CHAR * gap_cells, "gap"),
                ],
                width,
            )
        )

    rows.append(_fit([(_LABEL, "label")], width))

    return rows


_TOKEN_STYLES: dict[str, Optional[Style]] = {
    "x": Style(color=PALETTE.accent),
    "y": Style(color=PALETTE.medium),
    "z": Style(color=PALETTE.critical),
    "gap": Style(color=PALETTE.critical, bold=True),
    "label": Style(color=PALETTE.muted),
    "plain": Style(),
}


def mosca_timeline(
    x: float,
    y: float,
    z: float,
    width: Optional[int] = None,
) -> Group:
    """Render the Mosca timeline as a printable Rich :class:`~rich.console.Group`.

    Thin wrapper over :func:`mosca_timeline_segments`: each style token is
    mapped to a :mod:`ecdat.ui.theme` colour (``x`` → accent, ``y`` → medium,
    ``z`` → critical, ``gap`` → critical) and every row becomes a
    :class:`rich.text.Text`.

    Args:
        x: Data-lifetime component (years).
        y: Migration-time component (years).
        z: Quantum threat horizon (years).
        width: Row width in cells; defaults to 64 when ``None``.

    Returns:
        A :class:`~rich.console.Group` of timeline rows, ready for
        ``console.print()``.
    """
    resolved_width = 64 if width is None else width
    rows = mosca_timeline_segments(x, y, z, resolved_width)

    lines: List[Text] = []
    for row in rows:
        line = Text()
        for text, token in row:
            line.append(text, style=_TOKEN_STYLES.get(token, Style()))
        lines.append(line)

    return Group(*lines)