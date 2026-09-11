"""File-system and Git ingestion for the ECDAT scanner.

Walks local directories and clones Git repos to collect source files for
cryptographic analysis.  Also extracts manifest-level dependency metadata
from common package managers.

Public API:
    - :func:`ingest_local_directory` – walk a directory tree, yield source files.
    - :func:`ingest_git_url` – shallow-clone a Git repository, return local path.
    - :func:`ingest_manifest_dependencies` – extract dependency info from manifests.
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from collections.abc import Iterator
from pathlib import Path

from ecdat_core.detector import detect_language

# Directories to skip during directory traversal.
_SKIP_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        "node_modules",
        "venv",
        ".venv",
        "__pycache__",
        "dist",
        "build",
        "target",
        ".next",
    }
)

# Maximum file size in bytes — files larger than this are silently skipped.
_MAX_FILE_SIZE = 2 * 1024 * 1024  # 2 MB

# How many directory levels deep to scan for manifest files.
_MANIFEST_DEPTH = 3

# Timeout in seconds for git clone operations.
_GIT_CLONE_TIMEOUT = 60


def ingest_local_directory(path: str) -> Iterator[tuple[str, str, str]]:
    """Walk *path* and yield source files suitable for cryptographic scanning.

    Traverses the directory tree rooted at *path*, skipping well-known
    non-source directories (``.git``, ``node_modules``, ``venv``, etc.)
    and any file larger than 2 MB.  For each remaining file whose extension
    is recognised by :func:`~ecdat_core.detector.detect_language`, the file
    content is read and yielded together with its path and detected language.

    Files that cannot be decoded as UTF-8 are silently skipped so that a
    single binary file does not abort the entire scan.

    Args:
        path: Root directory to walk.

    Yields:
        Tuples of ``(file_path, content, language)`` for each successfully
        read source file.

    Raises:
        FileNotFoundError: If *path* does not exist or is not a directory.
    """
    root = Path(path)
    if not root.is_dir():
        raise FileNotFoundError(f"Not a directory: {path}")

    for dirpath, dirnames, filenames in os.walk(root):
        # Prune skipped directories **in-place** so os.walk does not descend.
        dirnames[:] = [
            d for d in dirnames if d not in _SKIP_DIRS
        ]

        for filename in filenames:
            file_path = os.path.join(dirpath, filename)

            # Skip oversized files.
            try:
                if os.path.getsize(file_path) > _MAX_FILE_SIZE:
                    continue
            except OSError:
                continue

            language = detect_language(file_path)
            if language is None:
                continue

            try:
                content = Path(file_path).read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue

            yield (file_path, content, language)


def ingest_git_url(git_url: str, workdir: str | None = None) -> str:
    """Shallow-clone a Git repository and return the local path.

    Runs ``git clone --depth 1 <url> <tmpdir>``.  If *workdir* is not
    provided a temporary directory is created via :func:`tempfile.mkdtemp`.

    Args:
        git_url: The repository URL to clone.
        workdir: Optional existing directory to clone into.  When ``None`` a
            temporary directory is created and its path is returned.

    Returns:
        The local filesystem path the repository was cloned into.

    Raises:
        RuntimeError: If the ``git clone`` command fails.  The exception
            message contains the stderr output from Git.
        subprocess.TimeoutExpired: If the clone exceeds 60 seconds.
    """
    if workdir is not None:
        target_dir = workdir
    else:
        target_dir = tempfile.mkdtemp(prefix="ecdat_clone_")

    try:
        result = subprocess.run(
            ["git", "clone", "--depth", "1", git_url, target_dir],
            capture_output=True,
            text=True,
            timeout=_GIT_CLONE_TIMEOUT,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"Git clone timed out after {_GIT_CLONE_TIMEOUT}s for {git_url}"
        ) from exc

    if result.returncode != 0:
        # Extract meaningful error lines from git stderr — strip progress
        # output like "Cloning into '...'..." that adds noise for end users.
        stderr_lines = result.stderr.strip().splitlines()
        error_lines = [line for line in stderr_lines if line.startswith("fatal:")]
        error_detail = (
            "; ".join(error_lines) if error_lines else result.stderr.strip()
        )
        raise RuntimeError(
            f"Could not clone repository: {error_detail}"
        )

    return target_dir


# ---------------------------------------------------------------------------
# Manifest dependency extraction
# ---------------------------------------------------------------------------

# Regex patterns per manifest format.  Each captures (name, version).
# Accepts ==, >=, <=, ~=, != and bare version specs after the name.
_REQ_TXT_RE = re.compile(
    r"^\s*(?P<name>[A-Za-z0-9_.-]+)"
    r"\s*(?:[<>=~!]+(?P<version>[^\s;#]+))?\s*(?:;.*)?\s*$"
)
_PKG_JSON_VER_RE = re.compile(r'"version"\s*:\s*"([^"]+)"')


def ingest_manifest_dependencies(path: str) -> list[dict]:
    """Scan *path* for common manifest files and extract dependency info.

    Searches up to :data:`_MANIFEST_DEPTH` levels deep for
    ``requirements.txt``, ``package.json``, ``pom.xml``, and ``go.mod``
    files.  For each found manifest a flat list of dependency records is
    produced using lightweight regex extraction — full dependency-graph
    resolution is intentionally out of scope.

    Args:
        path: Root directory to scan for manifest files.

    Returns:
        A list of dicts, each with keys ``name``, ``version`` (or
        ``"unknown"``), and ``manifest_file`` (absolute path).
    """
    root = Path(path)
    if not root.is_dir():
        raise FileNotFoundError(f"Not a directory: {path}")

    deps: list[dict] = []

    for manifest_path in _find_manifests(root):
        deps.extend(_extract_deps(manifest_path))

    return deps


# ---- private helpers ------------------------------------------------------


def _find_manifests(root: Path) -> list[Path]:
    """Return manifest file paths found within *root* up to ``_MANIFEST_DEPTH``."""
    manifests: list[Path] = []
    manifest_names = {"requirements.txt", "package.json", "pom.xml", "go.mod"}

    for dirpath, dirnames, filenames in os.walk(root):
        # Don't descend into well-known non-source dirs (node_modules, etc.).
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]

        # Calculate depth relative to root.
        depth = len(Path(dirpath).relative_to(root).parts)
        if depth >= _MANIFEST_DEPTH:
            dirnames.clear()  # stop descending
            continue

        for fname in filenames:
            if fname in manifest_names:
                manifests.append(Path(dirpath) / fname)

    return manifests


def _extract_deps(manifest_path: Path) -> list[dict]:
    """Extract dependency records from a single manifest file."""
    name = manifest_path.name
    extractors = {
        "requirements.txt": _extract_requirements_txt,
        "package.json": _extract_package_json,
        "pom.xml": _extract_pom_xml,
        "go.mod": _extract_go_mod,
    }
    extractor = extractors.get(name)
    if extractor is None:
        return []
    return extractor(manifest_path)


def _extract_requirements_txt(manifest: Path) -> list[dict]:
    """Parse ``requirements.txt`` for ``name==version`` pairs."""
    deps: list[dict] = []
    try:
        text = manifest.read_text(encoding="utf-8")
    except OSError:
        return deps

    for line in text.splitlines():
        m = _REQ_TXT_RE.match(line.strip())
        if not m:
            continue
        deps.append(
            {
                "name": m.group("name"),
                "version": m.group("version") or "unknown",
                "manifest_file": str(manifest),
            }
        )
    return deps


def _extract_package_json(manifest: Path) -> list[dict]:
    """Extract ``dependencies`` and ``devDependencies`` from ``package.json``."""
    import json

    deps: list[dict] = []
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return deps

    for dep_map_key in ("dependencies", "devDependencies"):
        dep_map = data.get(dep_map_key, {})
        if not isinstance(dep_map, dict):
            continue
        for name, version_spec in dep_map.items():
            deps.append(
                {
                    "name": name,
                    "version": str(version_spec) if version_spec else "unknown",
                    "manifest_file": str(manifest),
                }
            )
    return deps


def _extract_pom_xml(manifest: Path) -> list[dict]:
    """Extract ``<dependency>`` entries from a Maven ``pom.xml``."""
    deps: list[dict] = []
    try:
        text = manifest.read_text(encoding="utf-8")
    except OSError:
        return deps

    # Lightweight regex: find <dependency> blocks and pull groupId/artifactId/version.
    dep_blocks = re.findall(
        r"<dependency>(.*?)</dependency>", text, re.DOTALL
    )
    for block in dep_blocks:
        artifact_match = re.search(r"<artifactId>\s*(.+?)\s*</artifactId>", block)
        version_match = re.search(r"<version>\s*(.+?)\s*</version>", block)
        if artifact_match:
            deps.append(
                {
                    "name": artifact_match.group(1),
                    "version": version_match.group(1) if version_match else "unknown",
                    "manifest_file": str(manifest),
                }
            )
    return deps


def _extract_go_mod(manifest: Path) -> list[dict]:
    """Extract ``require`` entries from a Go ``go.mod`` file."""
    deps: list[dict] = []
    try:
        text = manifest.read_text(encoding="utf-8")
    except OSError:
        return deps

    # Match lines like:  github.com/foo/bar v1.2.3
    # Inside or outside a require block — grab all module-version pairs.
    in_require_block = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("require ("):
            in_require_block = True
            continue
        if in_require_block and stripped == ")":
            in_require_block = False
            continue
        if stripped.startswith("require ") and not in_require_block:
            # Single-line require: require github.com/foo/bar v1.2.3
            parts = stripped.split()
            if len(parts) == 3:
                deps.append(
                    {
                        "name": parts[1],
                        "version": parts[2],
                        "manifest_file": str(manifest),
                    }
                )
            continue
        if in_require_block:
            parts = stripped.split()
            if len(parts) >= 2:
                # Skip // indirect comments
                name = parts[0]
                version = parts[1]
                deps.append(
                    {
                        "name": name,
                        "version": version,
                        "manifest_file": str(manifest),
                    }
                )
    return deps
