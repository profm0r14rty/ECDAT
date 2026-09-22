"""PriorityList widget: selectable list of grouped priority actions.

Each row shows a risk chip, the family name, an ellipsised file path, the
artefact count, and the recommended replacement.  Pressing Enter on a row
posts a :class:`PriorityList.JumpToFindings` message so the parent screen
can navigate.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import List, Tuple

from rich.style import Style
from rich.text import Text
from textual.message import Message
from textual.widgets import OptionList
from textual.widgets.option_list import Option

from ecdat.services.viewmodel import PriorityAction
from ecdat.ui.render import risk_chip
from ecdat.ui.theme import PALETTE, strip_control_chars


def _ellipsis_middle(path: str, width: int = 40) -> str:
    """Ellipsise *path* in the middle, keeping the last two segments.

    ``"very/long/path/to/some/file.py"`` → ``"very/lo…/some/file.py"``.
    Returns *path* unchanged when it already fits *width*.
    """
    if len(path) <= width:
        return path
    parts = path.split("/")
    if len(parts) <= 2:
        return path[: width - 1] + "\u2026"
    right = "/".join(parts[-2:])
    left_budget = width - len(right) - 1  # -1 for the ellipsis sigil
    if left_budget < 3:
        return f"\u2026{right}"[:width]
    left = parts[0]
    i = 1
    while i < len(parts) - 2 and len(left) + 1 + len(parts[i]) <= left_budget:
        left = f"{left}/{parts[i]}"
        i += 1
    return f"{left}\u2026/{right}"


class PriorityList(OptionList):
    """Selectable list of grouped priority actions; Enter emits ``JumpToFindings``.

    Each row is built with a :func:`~ecdat.ui.render.risk_chip` and the
    action's family, ellipsised file path, count, and recommended algorithm.
    All dynamic content is wrapped in :class:`rich.text.Text` — never
    interpolated into markup strings.

    Args:
        actions: Priority actions to display (truncated to *limit*).
        limit: Maximum number of actions to show.
        id: DOM id.
        classes: Additional CSS classes.
    """

    class JumpToFindings(Message):
        """Message posted when the user presses Enter on an action row.

        The parent screen should handle this by navigating to the file
        that contains the selected family's findings.

        Args:
            family: The algorithm family (e.g. ``"RSA"``).
            file_path: The file path containing the findings.
        """

        def __init__(self, family: str, file_path: str) -> None:
            super().__init__()
            self.family: str = family
            """The algorithm family."""
            self.file_path: str = file_path
            """The file path containing the findings."""

    def __init__(
        self,
        actions: Sequence[PriorityAction],
        *,
        limit: int = 8,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        cls = f"{classes} priority-list" if classes else "priority-list"
        super().__init__(id=id, classes=cls)
        self.actions: List[PriorityAction] = list(actions)[:limit]

    def action_rows(self) -> List[Tuple[str, str, int, str]]:
        """Return each stored action as ``(family, file_path, count, recommended)``."""
        return [(a.family, a.file_path, a.count, a.recommended) for a in self.actions]

    def on_mount(self) -> None:
        """Populate the option list."""
        self.clear_options()
        if not self.actions:
            self.add_option(
                Option(
                    Text("No priority actions", style=Style(color=PALETTE.safe, italic=True)),
                    disabled=True,
                )
            )
            return
        for a in self.actions:
            self.add_option(self._build_option(a))

    def _build_option(self, action: PriorityAction) -> Option:
        """Build an :class:`Option` for one :class:`PriorityAction`."""
        prompt = Text()
        prompt.append(risk_chip(action.worst_risk))
        prompt.append("  ")
        path = _ellipsis_middle(action.file_path, 40)
        prompt.append(
            Text(
                strip_control_chars(
                    f"{action.family} \u2014 {path} ({action.count}) \u2192 {action.recommended}"
                )
            )
        )
        return Option(prompt)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Handle option selection: post ``JumpToFindings`` and stop the event."""
        event.stop()
        index = event.option_index
        if index < 0 or index >= len(self.actions):
            return
        action = self.actions[index]
        self.post_message(self.JumpToFindings(action.family, action.file_path))


__all__ = ["PriorityList"]