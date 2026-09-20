"""Console factory — the ONLY module allowed to create a Rich :class:`~rich.console.Console`.

Every :class:`~rich.console.Console` goes through :func:`make_console` so that
the palette theme, ``NO_COLOR``, ``FORCE_COLOR``, and terminal width are
applied consistently.  Direct ``Console()`` calls elsewhere are banned.
"""

from __future__ import annotations

import os
import sys
from typing import Optional

from rich.console import Console
from rich.theme import Theme

from ecdat.ui.theme import rich_theme


def _ensure_utf8_streams() -> None:
    """Reconfigure stdout/stderr to UTF-8 when possible.

    On Windows the default code page rarely supports box-drawing characters.
    When a stream has a ``.reconfigure`` method (Python 3.7+) and is not
    already UTF-8, we switch it to ``"utf-8"`` with ``errors="replace"`` so
    that Rich can render box-drawing characters without raising
    :exc:`UnicodeEncodeError`.

    Never raises — the reconfigure is best-effort.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            reconf = getattr(stream, "reconfigure", None)
            if reconf is None:
                continue
            current_enc = getattr(stream, "encoding", None)
            if current_enc is not None and current_enc.lower() not in (
                "utf-8",
                "utf8",
            ):
                reconf(encoding="utf-8", errors="replace")
        except Exception:
            pass  # best-effort


def make_console(
    *,
    stderr: bool = False,
    no_color: Optional[bool] = None,
    width: Optional[int] = None,
) -> Console:
    """Create a themed :class:`~rich.console.Console`.

    Callers outside ``ecdat/ui/`` use this factory; never construct a
    ``Console`` directly.

    Args:
        stderr: Write to stderr instead of stdout (default: stdout).
        no_color: Force colour off (``True``), on (``False``), or auto-detect
                  (``None`` / omitted).  Respects the ``NO_COLOR`` and
                  ``FORCE_COLOR`` env vars when *no_color* is ``None``.
        width: Terminal width in cells; ``None`` auto-detects.

    Returns:
        A configured :class:`~rich.console.Console`.
    """
    _ensure_utf8_streams()

    # Resolve no_color: explicit arg > NO_COLOR/FORCE_COLOR > auto-detect.
    if no_color is None:
        force = os.environ.get("FORCE_COLOR", "").strip()
        if force == "0" or os.environ.get("NO_COLOR", "").strip():
            no_color = True
        elif force and force != "0":
            no_color = False

    # Build colour system and no_color flags.
    if no_color is True:
        color_system = None
        _no_color = True
    elif no_color is False:
        color_system = "256"
        _no_color = False
    else:
        color_system = "auto"
        _no_color = None  # let Rich auto-detect

    theme: Optional[Theme]
    if _no_color is True:
        theme = None
    else:
        theme = rich_theme()

    return Console(
        file=sys.stderr if stderr else sys.stdout,
        theme=theme,
        color_system=color_system,
        no_color=_no_color,
        width=width,
        highlight=False,
    )


def is_interactive() -> bool:
    """Return ``True`` when stdout is connected to an interactive terminal.

    Delegates to Rich's :func:`~rich.console.detect_legacy_windows` and
    ``sys.stdout.isatty()``.  Returns ``False`` in CI or when piped.
    """
    return sys.stdout.isatty()


def supports_unicode(console: Console) -> bool:
    """Return ``True`` when the console's encoding supports Unicode box-drawing.

    This is almost always ``True`` on modern terminals (including Windows
    Terminal).  Falls back to ``False`` for legacy Windows consoles.
    """
    return console.legacy_windows is False or console.encoding == "utf-8"