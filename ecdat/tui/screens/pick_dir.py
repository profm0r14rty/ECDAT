"""The directory picker modal used by the Home screen.

Shows only directories (a :class:`~textual.widgets.DirectoryTree` subclass whose
``filter_paths`` drops files), starting at a caller-chosen directory.  Enter or
the Select button dismisses with the highlighted :class:`~pathlib.Path`;
Escape or Cancel dismisses with ``None``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, DirectoryTree, Label

# Widget ids.
_TREE_ID = "pick-tree"
_SELECT_ID = "pick-select"
_CANCEL_ID = "pick-cancel"


class _DirOnlyTree(DirectoryTree):
    """A directory tree that never shows files."""

    def filter_paths(self, paths: Iterable[Path]) -> Iterable[Path]:
        """Return only the directory entries from *paths*."""
        return [path for path in paths if path.is_dir()]


class PickDirScreen(ModalScreen[Optional[Path]]):
    """Modal directory picker returning the chosen path (or ``None``)."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(self, start: Optional[Path] = None) -> None:
        super().__init__()
        self._start = start or Path.cwd()

    def compose(self) -> ComposeResult:
        with Vertical(id="pick-body", classes="panel"):
            yield Label("Choose a folder to scan")
            yield _DirOnlyTree(self._start, id=_TREE_ID)
            with Horizontal(id="pick-buttons"):
                yield Button("Select", id=_SELECT_ID, variant="primary")
                yield Button("Cancel", id=_CANCEL_ID)

    def _cursor_path(self) -> Optional[Path]:
        """Return the path under the tree cursor, or ``None``."""
        tree = self.query_one(f"#{_TREE_ID}", _DirOnlyTree)
        node = tree.cursor_node
        data = getattr(node, "data", None)
        path = getattr(data, "path", None)
        return Path(path) if path is not None else None

    def on_directory_tree_directory_selected(
        self, event: DirectoryTree.DirectorySelected
    ) -> None:
        self.dismiss(Path(event.path))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == _SELECT_ID:
            self.dismiss(self._cursor_path())
        elif event.button.id == _CANCEL_ID:
            self.dismiss(None)

    def action_cancel(self) -> None:
        """Dismiss with no selection."""
        self.dismiss(None)


__all__ = ["PickDirScreen"]
