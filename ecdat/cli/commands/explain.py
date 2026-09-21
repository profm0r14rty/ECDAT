"""``ecdat explain`` — explain an algorithm in plain English.

Looks up a signature entry by name (or family) and renders a panel describing
what it is, its quantum status, whether it is classically broken, how ECDAT
scores it with Mosca's inequality, the recommended NIST replacement, and the
languages ECDAT detects it in.

The knowledge base is read through the public
:mod:`ecdat_core.signature_loader` API.  Every dynamic value is wrapped in
:class:`rich.text.Text` so knowledge-base text is never parsed as markup.

Note:
    :class:`~ecdat_core.signature_loader.SignatureEntry` has no ``aliases``
    field, so the lookup covers ``name`` and ``family`` — the fields the real
    model actually exposes.
"""

from __future__ import annotations

import argparse
import difflib
from typing import List

from rich.panel import Panel
from rich.text import Text

from ecdat.ui.theme import PALETTE, make_console
from ecdat_core.signature_loader import SignatureEntry, get_all_signatures

NAME = "explain"


def register(subparsers: "argparse._SubParsersAction") -> None:
    """Attach the ``explain`` subcommand to *subparsers*."""
    parser = subparsers.add_parser(
        "explain",
        help="Explain an algorithm in plain English",
        description=(
            "Explain a signature by name or family: what it is, its quantum "
            "status, how Mosca's inequality scores it, and what replaces it."
        ),
    )
    parser.add_argument(
        "name",
        help="Signature name or family to explain (case-insensitive)",
    )


# One-paragraph, static explanation of the scoring model.  Kept as a module
# constant so the wording is consistent across every explained algorithm.
_MOSCA_PARAGRAPH = (
    "ECDAT scores this with Mosca's inequality, X + Y > Z: X is the time to "
    "migrate away from the algorithm, Y is how long the protected data must "
    "stay secret, and Z is the estimated arrival of a cryptographically "
    "relevant quantum computer. When X + Y exceeds Z the artefact is already "
    "exposed, and the urgency ratio (X + Y) / Z classifies it from low through "
    "critical."
)


def _find_matches(name: str) -> List[SignatureEntry]:
    """Return entries whose name or family matches *name* case-insensitively."""
    needle = name.strip().lower()
    return [
        entry
        for entry in get_all_signatures()
        if entry.name.lower() == needle or entry.family.lower() == needle
    ]


def _quantum_status(entry: SignatureEntry) -> str:
    """Return the plain-English quantum status for *entry*.

    - Symmetric families with a ``min_quantum_safe_key_bits`` threshold are
      described as weakened by Grover's algorithm up to that key size.
    - Otherwise quantum-vulnerable entries are broken by Shor's algorithm.
    - Everything else is not affected.
    """
    if entry.min_quantum_safe_key_bits is not None:
        return (
            "weakened by Grover's algorithm \u2014 needs at least "
            f"{entry.min_quantum_safe_key_bits}-bit keys"
        )
    if entry.quantum_vulnerable:
        return "broken by Shor's algorithm"
    return "not affected by quantum algorithms (quantum-safe)"


def _build_body(entry: SignatureEntry) -> Text:
    """Build the panel body as a :class:`~rich.text.Text` (markup-safe).

    Args:
        entry: The matched signature entry.

    Returns:
        A styled :class:`~rich.text.Text` ready to place inside a panel.
    """
    body = Text()

    def section(title: str) -> None:
        body.append(f"{title}\n", style=f"bold {PALETTE.accent}")

    def field(label: str, value: str) -> None:
        body.append(f"{label}: ", style=f"bold {PALETTE.text}")
        body.append(f"{value}\n")

    # What it is.
    section("What it is")
    field("Family", entry.family)
    body.append("\n")

    # Quantum status.
    section("Quantum status")
    field("Status", _quantum_status(entry))
    if entry.classically_broken:
        body.append("Warning: ", style=f"bold {PALETTE.critical}")
        body.append(
            "already broken today by classical attacks, independent of "
            "quantum computing \u2014 do not treat it as quantum-safe.\n",
            style=PALETTE.critical,
        )
    body.append("\n")

    # How ECDAT scores it.
    section("How ECDAT scores it")
    body.append(_MOSCA_PARAGRAPH + "\n")
    body.append("\n")

    # Recommended replacement.
    section("Recommended replacement")
    field("Algorithm", entry.pqc_recommendation.algorithm)
    field("FIPS reference", entry.pqc_recommendation.fips_reference)
    body.append("\n")

    # Detection coverage.
    section("Detected in languages")
    body.append(", ".join(sorted(entry.patterns)) + "\n")

    return body


def _render_panel(entry: SignatureEntry) -> Panel:
    """Render the explanation panel for a single matched entry."""
    return Panel(
        _build_body(entry),
        title=Text(f"ecdat explain \u00b7 {entry.name}"),
        title_align="left",
        border_style=PALETTE.border,
        padding=(1, 2),
    )


def run(args: object) -> int:
    """Execute the ``explain`` subcommand.

    Args:
        args: Parsed arguments with attribute ``name``.

    Returns:
        Exit code: 0 when exactly one entry matched; 2 when several or none
        matched (several → the candidates are listed; none → close matches are
        suggested).
    """
    name: str = getattr(args, "name", "")
    out = make_console()

    matches = _find_matches(name)

    if len(matches) == 1:
        out.print(_render_panel(matches[0]))
        return 0

    if len(matches) > 1:
        out.print(
            Text(
                f"{len(matches)} signatures match {name!r}; "
                f"be more specific:"
            )
        )
        for entry in sorted(matches, key=lambda e: e.name):
            out.print(Text(f"  {entry.name} \u2014 {entry.family}"))
        return 2

    # No match — offer close suggestions from the real knowledge base.
    names = [entry.name for entry in get_all_signatures()]
    suggestions = difflib.get_close_matches(
        name.strip().lower(), [n.lower() for n in names], n=3
    )
    # Map lowercased suggestions back to their canonical names.
    by_lower = {n.lower(): n for n in names}
    canonical = [by_lower[s] for s in suggestions]

    if canonical:
        out.print(Text(f"No signature named {name!r}. Did you mean:"))
        for suggestion in canonical:
            out.print(Text(f"  {suggestion}"))
    else:
        out.print(
            Text(
                f"No signature named {name!r} "
                f"(0 of {len(names)} signatures)."
            )
        )
    return 2
