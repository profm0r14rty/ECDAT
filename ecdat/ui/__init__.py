"""ECDAT app-layer UI package — theme tokens, console factory, Rich renderers.

This package holds every terminal-presentation concern for the ``ecdat`` app
layer.  It is intentionally separate from ``ecdat_core`` (the engine), which
must stay UI-free.

Public modules:
    - :mod:`ecdat.ui.theme` — frozen palette, risk metadata, the Rich theme,
      and the single sanctioned :func:`~ecdat.ui.theme.make_console` factory.
    - :mod:`ecdat.ui.render` — Rich renderers built from plain values.
"""
