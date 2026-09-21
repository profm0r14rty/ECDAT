"""ECDAT app-layer UI package — theme tokens, console factory, renderers, and ASCII art.

This package holds every terminal-presentation concern for the ``ecdat`` app
layer.  It is intentionally separate from ``ecdat_core`` (the engine), which
must stay UI-free.

Public modules:
    - :mod:`ecdat.ui.theme` — frozen palette, risk metadata, the Rich theme.
    - :mod:`ecdat.ui.console` — the single sanctioned
      :func:`~ecdat.ui.console.make_console` factory.
    - :mod:`ecdat.ui.render` — Rich renderers built from plain values.
    - :mod:`ecdat.ui.banner` — the gradient ECDAT banner.
    - :mod:`ecdat.ui.motion` — the animation policy and motion helpers.
    - :mod:`ecdat.ui.art3d` / :mod:`ecdat.ui.art_static` /
      :mod:`ecdat.ui.art_text` — the pure 3D/ASCII art engine.
"""
