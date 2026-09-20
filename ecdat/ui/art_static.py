"""Static ASCII art for the results screens (pure, dependency-free). Every emblem is 9 rows x 19 cols."""
from __future__ import annotations

from collections.abc import Mapping

SAFE_LOCK = (
    r'      .-"""-.      ',
    r'     /  .-.  \     ',
    r'     | |   | |     ',
    r"   .-'-'---'-'-.   ",
    r'   |   .---.   |   ',
    r'   |   | o |   |   ',
    r"   |   '-.-'   |   ",
    r'   |     |     |   ',
    r"   '-----------'   ",
)
WARN_LOCK = (
    r'      .-"""-.      ',
    r'     /  .-.  \     ',
    r'     | |   | |     ',
    r"   .-'-'---'-'-.   ",
    r'   |   .-\-.   |   ',
    r'   |   | ! |   |   ',
    r"   |   '-/-'   |   ",
    r'   |     |     |   ',
    r"   '-----------'   ",
)
CRIT_LOCK = (
    r'        .-"""-.    ',
    r'       /  .-.  \   ',
    r'       | |   |     ',
    r"   .-'-'---'-'-.   ",
    r'   |   .---.   |   ',
    r'   |   | X |   |   ',
    r"   |   '-.-'   |   ",
    r'   |     |     |   ',
    r"   '-----------'   ",
)


def verdict(counts: Mapping[str, int]) -> str:
    """'crit' | 'warn' | 'safe' | 'empty' from a risk-level → count mapping."""
    total = sum(counts.values())
    if total == 0:
        return "empty"
    if counts.get("critical", 0) >= 1:
        return "crit"
    if counts.get("high", 0) + counts.get("medium", 0) >= 1:
        return "warn"
    return "safe"


def emblem_for(v: str) -> tuple[str, ...]:
    return {"crit": CRIT_LOCK, "warn": WARN_LOCK}.get(v, SAFE_LOCK)


def headline_for(counts: Mapping[str, int], files: int = 0) -> str:
    v = verdict(counts)
    if v == "crit":
        return f"{counts.get('critical', 0)} CRITICAL · {counts.get('high', 0)} HIGH — migrate before your next review"
    if v == "warn":
        return f"{counts.get('high', 0)} HIGH · {counts.get('medium', 0)} MEDIUM — plan your PQC migration"
    if v == "safe":
        return "Looking good — no urgent quantum exposure"
    return f"No cryptographic artefacts detected in {files} files"
