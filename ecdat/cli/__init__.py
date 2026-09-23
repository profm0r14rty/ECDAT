"""ECDAT command-line interface.

The :func:`main` entry point (wired as the ``ecdat`` console script and used by
``python -m ecdat``) lives in :mod:`ecdat.cli.main`; it is re-exported here so
both ``from ecdat.cli import main`` and ``from ecdat.cli.main import main``
resolve to the same callable.  Importing this package stays cheap — Rich, the
scanner engine, and Textual are all imported lazily by the command modules.
"""

from __future__ import annotations

from ecdat.cli.main import main

__all__ = ["main"]
