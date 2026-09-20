"""Access to the bundled sample project shipped inside the ``ecdat`` wheel.

The demo project is a deliberately insecure copy of the engine's
``showcase_repo`` fixture.  It lives as package data, so it must be reached
through :mod:`importlib.resources` — never through ``__file__`` tricks, which
break inside zip imports and frozen distributions.

Public API:
    - :func:`demo_source` — the packaged sample as a :class:`Traversable`.
    - :func:`demo_project` — context manager yielding a real, writable copy of
      the sample in a temporary directory.
    - :func:`materialize_demo` — copy the sample to a caller-chosen directory.
"""

from __future__ import annotations

import importlib.resources
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Iterator

if TYPE_CHECKING:  # pragma: no cover - typing only
    from importlib.resources.abc import Traversable

__all__ = ["demo_source", "demo_project", "materialize_demo"]


def demo_source() -> "Traversable":
    """Return the bundled demo project as an importlib resource.

    Returns:
        A :class:`Traversable` for the ``ecdat/demo_project`` package-data
        directory.  It may or may not be backed by a real filesystem path.
    """
    return importlib.resources.files("ecdat") / "demo_project"


def _copy_tree(source: "Traversable", destination: Path) -> None:
    """Recursively copy a :class:`Traversable` tree onto *destination*.

    Walks the traversable directly (``iterdir``) rather than forcing it onto
    disk with ``importlib.resources.as_file`` — this keeps the copy working
    for non-filesystem loaders and avoids any lingering temp extraction.
    """
    destination.mkdir(parents=True, exist_ok=True)
    for child in source.iterdir():
        target = destination / child.name
        if child.is_dir():
            _copy_tree(child, target)
        else:
            target.write_bytes(child.read_bytes())


def materialize_demo(destination: Path) -> Path:
    """Copy the bundled demo project into *destination* and return it.

    Any pre-existing *destination* is replaced so the result is always a
    clean, complete copy.

    Args:
        destination: Directory to (re)create and fill with the sample.

    Returns:
        The *destination* path, for convenient chaining.
    """
    if destination.exists():
        shutil.rmtree(destination)
    _copy_tree(demo_source(), destination)
    return destination


@contextmanager
def demo_project() -> Iterator[Path]:
    """Yield a writable copy of the bundled demo project.

    The copy lives in a :class:`~tempfile.TemporaryDirectory` and is deleted
    when the context exits — callers can mutate it freely without touching the
    installed package.
    """
    with tempfile.TemporaryDirectory(prefix="ecdat-demo-") as tmpdir:
        destination = Path(tmpdir) / "demo_project"
        _copy_tree(demo_source(), destination)
        yield destination
