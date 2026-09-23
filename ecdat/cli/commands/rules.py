"""``ecdat rules`` — browse the cryptographic signature knowledge base.

Lists the detection signatures ECDAT ships with, optionally filtered by a
substring query and/or by family/language.  The knowledge base is loaded
through the public :mod:`ecdat_core.signature_loader` API — no fields are
invented here, and ``signatures.json`` is never written to.

Output discipline: ``--json`` writes only the JSON payload to stdout; the
human-readable table (itself the payload for this command) goes to stdout and
errors go to stderr.  Every dynamic value is wrapped in
:class:`rich.text.Text` so untrusted signature text is never parsed as markup.

Note:
    :class:`~ecdat_core.signature_loader.SignatureEntry` has no ``aliases``
    field — the real model exposes ``name`` and ``family`` only — so the
    ``QUERY`` substring search covers name and family.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Optional, Sequence

from rich.table import Table
from rich.text import Text

from ecdat.ui.theme import PALETTE, make_console
from ecdat_core.signature_loader import SignatureEntry, get_all_signatures

NAME = "rules"


def register(subparsers: "argparse._SubParsersAction") -> None:
    """Attach the ``rules`` subcommand to *subparsers*."""
    parser = subparsers.add_parser(
        "rules",
        help="Browse the cryptographic signature knowledge base",
        description=(
            "List the detection signatures ECDAT ships with, optionally "
            "filtered by a case-insensitive substring and/or family/language."
        ),
    )
    parser.add_argument(
        "query",
        nargs="?",
        default=None,
        help="Case-insensitive substring over signature name/family",
    )
    parser.add_argument(
        "--family",
        default=None,
        help="Only signatures whose family contains this value",
    )
    parser.add_argument(
        "--language",
        default=None,
        help="Only signatures with detection patterns for this language",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit the results as JSON on stdout",
    )


def _matches(
    entry: SignatureEntry,
    query: Optional[str],
    family: Optional[str],
    language: Optional[str],
) -> bool:
    """Return whether *entry* passes the query/family/language filters.

    Filters are AND-combined; an unset filter imposes no constraint.  ``query``
    is a case-insensitive substring match over the name and family.
    """
    if family is not None and family.lower() not in entry.family.lower():
        return False
    if language is not None:
        langs = {lang.lower() for lang in entry.patterns}
        if language.lower() not in langs:
            return False
    if query is not None:
        needle = query.lower()
        if needle not in entry.name.lower() and needle not in entry.family.lower():
            return False
    return True


def _as_dict(entry: SignatureEntry) -> dict:
    """Serialise an entry to the JSON payload shape for ``--json``."""
    return {
        "name": entry.name,
        "family": entry.family,
        "languages": sorted(entry.patterns),
        "quantum_vulnerable": entry.quantum_vulnerable,
        "classically_broken": entry.classically_broken,
        "recommended_algorithm": entry.pqc_recommendation.algorithm,
        "fips_reference": entry.pqc_recommendation.fips_reference,
    }


def _yes_no(value: bool) -> Text:
    """Render a boolean as a coloured ``yes``/``no`` :class:`Text`."""
    color = PALETTE.critical if value else PALETTE.muted
    return Text("yes" if value else "no", style=color)


def _table(entries: Sequence[SignatureEntry]) -> Table:
    """Build the signatures table for the human-readable output."""
    table = Table(
        title=None,
        border_style=PALETTE.border,
        header_style=f"bold {PALETTE.accent}",
        expand=False,
        pad_edge=True,
    )
    table.add_column("Name")
    table.add_column("Family")
    table.add_column("Languages")
    table.add_column("Quantum-vulnerable")
    table.add_column("Classically broken")
    table.add_column("Recommended replacement")

    for entry in entries:
        table.add_row(
            Text(entry.name),
            Text(entry.family),
            Text(", ".join(sorted(entry.patterns))),
            _yes_no(entry.quantum_vulnerable),
            _yes_no(entry.classically_broken),
            Text(entry.pqc_recommendation.algorithm),
        )
    return table


def run(args: object) -> int:
    """Execute the ``rules`` subcommand.

    Args:
        args: Parsed arguments with attributes ``query``, ``family``,
            ``language`` and ``json``.

    Returns:
        Exit code (always 0 — an empty result set is not an error).
    """
    query: Optional[str] = getattr(args, "query", None)
    family: Optional[str] = getattr(args, "family", None)
    language: Optional[str] = getattr(args, "language", None)
    as_json: bool = bool(getattr(args, "json", False))

    all_entries = get_all_signatures()
    selected = [e for e in all_entries if _matches(e, query, family, language)]

    if as_json:
        payload = [_as_dict(e) for e in selected]
        sys.stdout.write(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
        return 0

    out = make_console()

    if not selected:
        out.print(
            Text(
                f"No signatures match the given filters "
                f"(0 of {len(all_entries)} signatures)."
            )
        )
        return 0

    out.print(Text(f"{len(selected)} of {len(all_entries)} signatures"))
    out.print(_table(selected))
    return 0
