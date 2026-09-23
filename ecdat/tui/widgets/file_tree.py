"""FileTreePane widget: a Tree showing the scanned repo's files and findings.

Each file node is annotated with its finding count and worst-risk colour.
Selecting a file node posts a :class:`FileTreePane.FileSelected` message so
the parent screen can navigate.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from rich.style import Style
from rich.text import Text
from textual.message import Message
from textual.widgets import Tree

from ecdat.services.viewmodel import ScanVM
from ecdat.ui.theme import RISK_COLORS, RISK_INDEX, strip_control_chars


# ---------------------------------------------------------------------------
# Common-prefix helper
# ---------------------------------------------------------------------------


def _common_dir_prefix(parts_lists: List[List[str]]) -> List[str]:
    """Compute the longest common leading *directory* segments across all paths.

    The filename (last segment) of each path is excluded so the prefix stops at
    the last common parent directory.  An empty-by_file case should be guarded
    by the caller.

    Examples::

        [['a','b','x.py'], ['a','b','y.js']]          → ['a','b']
        [['prj','auth','login.py']]                    → ['prj','auth']
        [['src','a.py'], ['tests','b.py']]             → []
        [['setup.py']]                                 → []
    """
    if not parts_lists:
        return []
    # Exclude filename; compare only directory parts.
    dir_parts = [p[:-1] for p in parts_lists]
    # Guard against paths that are root-level files (no directory parts).
    if not dir_parts[0]:
        return []
    common: List[str] = []
    min_len = min(len(dp) for dp in dir_parts)
    for i in range(min_len):
        segment = dir_parts[0][i]
        if all(dp[i] == segment for dp in dir_parts):
            common.append(segment)
        else:
            break
    return common


# ---------------------------------------------------------------------------
# FileTreePane
# ---------------------------------------------------------------------------


class FileTreePane(Tree):
    """A tree view of the scanned repo's directories and files.

    Directory nodes show their name and the cumulative finding count beneath
    them.  File nodes show their name, finding count, and are coloured by the
    worst risk level among findings in that file.  Selecting a file node posts
    a :class:`FileSelected` message.

    All dynamic content (paths, names, target) is wrapped in
    :class:`rich.text.Text` — never interpolated into markup strings.

    Args:
        vm: The scan view-model; ``vm.by_file`` drives the tree.
        id: DOM id (defaults to ``"file-tree"``).
        classes: Additional CSS classes appended to ``"file-tree-pane"``.
    """

    class FileSelected(Message):
        """Message posted when the user selects a file in the tree.

        The parent screen should handle this by navigating to the file that
        contains the findings.

        Args:
            file_path: The original (full) file path from ``ScanVM.by_file``.
            family: The algorithm family of the worst-risk finding, or ``""``.
        """

        def __init__(self, file_path: str, family: str = "") -> None:
            super().__init__()
            self.file_path: str = file_path
            """The original file path from the scan."""
            self.family: str = family
            """The algorithm family, or ``""``."""

    def __init__(
        self,
        vm: ScanVM,
        *,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        cls = f"{classes} file-tree-pane" if classes else "file-tree-pane"
        # Root label is the scan target — attacker-controlled → wrap in Text.
        root_label = (
            Text(strip_control_chars(vm.target))
            if isinstance(vm.target, str)
            else vm.target
        )
        super().__init__(root_label, id=id or "file-tree", classes=cls)
        self._vm: ScanVM = vm
        self._file_records: List[Tuple[str, str]] = []  # (display_name, original_path)

    # ------------------------------------------------------------------
    # Public helpers (consumed by tests / parent screens)
    # ------------------------------------------------------------------

    def top_level_names(self) -> List[str]:
        """Return sorted names of every top-level directory or file under the root.

        Names are extracted from the plain-text representation of each child
        label, stripping the ``/`` suffix (directories) and ``(n)`` count.
        """
        names: List[str] = []
        for child in self.root.children:
            if child is None:
                continue
            label = child.label
            plain = label.plain if isinstance(label, Text) else str(label)
            # Label forms:  "auth/ (5)"  (dir)  or  "login.py (3)"  (file)
            # Strip the " (N)" count suffix first.
            base = plain.rsplit(" (", 1)[0] if " (" in plain else plain
            name = base.rstrip("/")  # directory trailing-slash "auth/" → "auth"
            names.append(name)
        return sorted(names, key=str.lower)

    def file_nodes(self) -> List[Tuple[str, str]]:
        """Return ``(display_name, original_file_path)`` for every file leaf.

        ``display_name`` is the plain-text label (e.g. ``"login.py (3)"``);
        ``original_file_path`` is the key from ``ScanVM.by_file``.
        """
        return list(self._file_records)

    # ------------------------------------------------------------------
    # Mount — build the tree from vm.by_file
    # ------------------------------------------------------------------

    def on_mount(self) -> None:
        """Populate the tree from ``self._vm.by_file``."""
        by_file = self._vm.by_file
        if not by_file:
            return

        # 1. Normalise paths and split into segment lists.
        paths = list(by_file.keys())
        parts_lists: List[List[str]] = [
            p.replace("\\", "/").split("/") for p in paths
        ]

        # 2. Compute common prefix, strip it.
        common_prefix = _common_dir_prefix(parts_lists)
        prefix_len = len(common_prefix)

        # 3. Build an intermediate dict-tree of {name: {children:, count:}}.
        intermediate: dict = {"children": {}, "count": 0}

        for file_path, findings in by_file.items():
            norm = file_path.replace("\\", "/")
            parts = norm.split("/")

            # Strip the common prefix.
            if prefix_len <= len(parts):
                display_parts = parts[prefix_len:]
            else:
                display_parts = parts[:]

            # Determine worst risk + associated family.
            worst_idx: int = 99
            worst_risk_level: str = ""
            worst_family: Optional[str] = None
            for fm in findings:
                idx = RISK_INDEX.get(fm.risk_level, 99)
                if idx < worst_idx:
                    worst_idx = idx
                    worst_risk_level = fm.risk_level
                    worst_family = fm.family

            count = len(findings)

            # Walk / create intermediate directory nodes.
            cur = intermediate
            for segment in display_parts[:-1]:
                if segment not in cur["children"]:
                    cur["children"][segment] = {"children": {}, "count": 0}
                cur = cur["children"][segment]

            # Leaf node.
            leaf_name = display_parts[-1]
            cur["children"][leaf_name] = {
                "children": {},
                "count": count,
                "worst_risk": worst_risk_level,
                "original_path": file_path,
                "family": worst_family,
                "is_file": True,
            }

        # 4. Bottom-up: directory counts = sum of children.
        self._compute_counts(intermediate)

        # 5. Render intermediate dict-tree → Textual Tree nodes.
        self._render_tree(self.root, intermediate)

        # 6. Expand root + first directory level.
        self.root.expand()
        for child in self.root.children:
            if child is None:
                continue
            # Directories have data=None (or dict without "is_file").
            if not isinstance(child.data, dict) or not child.data.get("is_file"):
                child.expand()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _compute_counts(self, node_data: dict) -> int:
        """Recursively sum finding counts for every directory node.

        Returns *node_data["count"]* after updating it to include all
        descendants.
        """
        total: int = node_data.get("count", 0)
        for child in node_data.get("children", {}).values():
            total += self._compute_counts(child)
        node_data["count"] = total
        return total

    def _render_tree(self, parent_node, node_data: dict) -> None:
        """Recursively render the intermediate tree into Textual Tree nodes."""
        children = node_data.get("children", {})

        # Sort: directories first, then files; each group case-insensitive.
        dirs: List[Tuple[str, dict]] = []
        files: List[Tuple[str, dict]] = []
        for name, child in children.items():
            if child.get("is_file"):
                files.append((name, child))
            else:
                dirs.append((name, child))
        dirs.sort(key=lambda x: x[0].lower())
        files.sort(key=lambda x: x[0].lower())

        for name, child in dirs + files:
            if child.get("is_file"):
                # --- File leaf ---
                count = child["count"]
                label_text = Text(strip_control_chars(name))
                label_text.append(Text(f" ({count})"))
                worst_risk = child.get("worst_risk", "")
                color = RISK_COLORS.get(worst_risk)
                if color:
                    label_text.stylize(Style(color=color))

                data: Optional[dict] = {
                    "file_path": child["original_path"],
                    "family": child.get("family"),
                }
                node = parent_node.add(label_text, data=data)
                # Record for file_nodes().
                self._file_records.append((label_text.plain, child["original_path"]))
            else:
                # --- Directory ---
                count = child["count"]
                label_text = Text(strip_control_chars(f"{name}/ ({count})"))
                label_text.stylize("bold")
                node = parent_node.add(label_text, data=None)
                self._render_tree(node, child)

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        """Handle node selection: post ``FileSelected`` for file nodes."""
        event.stop()
        node = event.node
        if node is None:
            return
        data = node.data
        if isinstance(data, dict) and "file_path" in data:
            family = data.get("family") or ""
            self.post_message(self.FileSelected(data["file_path"], family))


__all__ = ["FileTreePane"]