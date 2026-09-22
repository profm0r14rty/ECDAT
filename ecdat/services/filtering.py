"""Pure filtering and sorting for :class:`~ecdat.services.viewmodel.FindingVM`.

This module has **no** Textual or Rich imports — it is trivially unit-testable
and can be reused by any view layer.  Every function returns a new list and
never mutates its input.

The two entry points are deliberately symmetric to how the Findings tab works:
``filter_findings`` narrows the visible set (severity chips, free-text search,
and the exact ``file`` / ``family`` filters a jump-to-findings request carries),
and ``sort_findings`` reorders whatever survives.

Public API:
    - :data:`SORT_MODES` — the sort modes, in cycle order.
    - :data:`SORT_LABELS` — human-readable names for each mode.
    - :func:`filter_findings` — narrow by level / query / file / family.
    - :func:`sort_findings` — reorder by urgency / file / algorithm / risk.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from typing import List, Literal

from ecdat.services.viewmodel import FindingVM

SortMode = Literal["urgency", "file", "algorithm", "risk"]

#: The sort modes, in the order the Findings tab cycles through them with ``o``.
SORT_MODES: tuple[str, ...] = ("urgency", "file", "algorithm", "risk")

#: Human-readable label for each sort mode (shown in the pane's status bar).
SORT_LABELS: dict[str, str] = {
    "urgency": "Urgency",
    "file": "File",
    "algorithm": "Algorithm",
    "risk": "Risk",
}

# Severity ordering — lower is worse.  Mirrors the viewmodel's own ordering so
# a "risk" sort matches the order the Overview already presents findings in.
_RISK_ORDER: dict[str, int] = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
    "quantum-safe": 4,
}


def filter_findings(
    findings: Sequence[FindingVM],
    *,
    levels: Collection[str] | None = None,
    query: str = "",
    file: str | None = None,
    family: str | None = None,
) -> List[FindingVM]:
    """Narrow *findings* by severity, free-text query, file, and family.

    Filters combine with AND.  The free-text *query* is a case-insensitive
    substring match against a finding's algorithm, file path, or family.  The
    *file* and *family* filters are **exact** matches (they come from the
    priority list and the file tree, which already know the precise values).

    Args:
        findings: The findings to filter (never mutated).
        levels: When given, only these risk levels pass.  An empty collection
            matches nothing — use ``None`` to disable the filter entirely.
        query: Case-insensitive substring; blank disables the filter.
        file: Exact file path to keep; ``None`` disables the filter.
        family: Exact algorithm family to keep; ``None`` disables the filter.

    Returns:
        A new list of the findings that satisfy every active filter, in the
        original input order.
    """
    needle = query.strip().lower()
    result: List[FindingVM] = []

    for finding in findings:
        if levels is not None and finding.risk_level not in levels:
            continue
        if file is not None and finding.file_path != file:
            continue
        if family is not None and finding.family != family:
            continue
        if needle and not _matches_query(finding, needle):
            continue
        result.append(finding)

    return result


def sort_findings(
    findings: Sequence[FindingVM],
    mode: str = "urgency",
) -> List[FindingVM]:
    """Return *findings* reordered for *mode* (stable, input never mutated).

    Modes:

    - ``"urgency"`` — highest :attr:`~FindingVM.urgency_ratio` first.
    - ``"file"`` — by file path, then line number.
    - ``"algorithm"`` — by algorithm name, then file, then line.
    - ``"risk"`` — worst risk level first, then urgency, then file, line.

    An unknown *mode* falls back to ``"urgency"``.  Python's sort is stable, so
    findings that compare equal keep their incoming relative order.

    Args:
        findings: The findings to sort (never mutated).
        mode: One of :data:`SORT_MODES`.

    Returns:
        A new, sorted list.
    """
    ordered = list(findings)
    if mode == "file":
        ordered.sort(key=lambda f: (f.file_path, f.line))
    elif mode == "algorithm":
        ordered.sort(key=lambda f: (f.algorithm.lower(), f.file_path, f.line))
    elif mode == "risk":
        ordered.sort(
            key=lambda f: (
                _RISK_ORDER.get(f.risk_level, 99),
                -f.urgency_ratio,
                f.file_path,
                f.line,
            )
        )
    else:  # "urgency" and any unknown mode
        ordered.sort(key=lambda f: (-f.urgency_ratio, f.file_path, f.line))
    return ordered


def _matches_query(finding: FindingVM, needle: str) -> bool:
    """Return whether *finding* contains the already-lowercased *needle*."""
    return (
        needle in finding.algorithm.lower()
        or needle in finding.file_path.lower()
        or needle in finding.family.lower()
    )


__all__ = [
    "SORT_MODES",
    "SORT_LABELS",
    "SortMode",
    "filter_findings",
    "sort_findings",
]
