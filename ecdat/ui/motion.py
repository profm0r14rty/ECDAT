"""Motion / animation policy — respects reduced-motion, CI, and env overrides.

Exports a single function: :func:`animations_enabled`.
"""

from __future__ import annotations

import os
from typing import Optional


def animations_enabled(
    reduce_motion: bool = False,
    env: Optional[dict[str, str]] = None,
) -> bool:
    """Return ``True`` when animations should play.

    Resolution order (first match wins):

    1. ``ECDAT_ANIM`` env var — ``"0"``/``"off"``/``"false"``/``"no"`` →
       ``False``; ``"1"``/``"on"``/``"true"``/``"yes"`` → ``True``.
    2. If *reduce_motion* is ``True`` → ``False``.
    3. If running under CI (``CI`` env var set to anything truthy) → ``False``.
    4. If running under pytest (``PYTEST_CURRENT_TEST`` set) → ``False``.
    5. If ``TERM`` is ``"dumb"`` → ``False``.
    6. Otherwise → ``True`` (default: animations on).

    Args:
        reduce_motion: Caller-level reduced-motion flag (e.g. from
                       ``prefers-reduced-motion``).
        env: Environment dict; defaults to :data:`os.environ`.

    Returns:
        ``True`` if animations should play.
    """
    if env is None:
        env = os.environ

    # 1. Explicit override via ECDAT_ANIM.
    anim = env.get("ECDAT_ANIM", "").strip().lower()
    if anim:
        if anim in ("0", "off", "false", "no"):
            return False
        if anim in ("1", "on", "true", "yes"):
            return True

    # 2. Reduced-motion flag.
    if reduce_motion:
        return False

    # 3. CI environment.
    if env.get("CI", "").strip():
        return False

    # 4. Pytest.
    if env.get("PYTEST_CURRENT_TEST", "").strip():
        return False

    # 5. Dumb terminal.
    if env.get("TERM", "").strip().lower() == "dumb":
        return False

    # 6. Default: animations on.
    return True