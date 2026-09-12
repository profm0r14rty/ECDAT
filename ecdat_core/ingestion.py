"""File-system and Git ingestion for the ECDAT scanner.

Walks local directories and clones Git repos to collect source files for
cryptographic analysis.  Also extracts manifest-level dependency metadata
from common package managers.

Security model (see AGENTS.md "Security Conventions"):

- Git URLs are validated **before** any ``git clone`` is attempted: only
  ``https://`` is accepted, every address the hostname resolves to must be
  public (private/loopback/link-local/reserved/multicast targets are
  rejected — SSRF protection), an optional ``GIT_URL_ALLOWED_HOSTS``
  allowlist further restricts hosts, and a post-clone
  ``GIT_URL_MAX_SIZE_MB`` ceiling aborts oversized repos cleanly.
- Local paths must resolve (symlinks followed via ``realpath``) inside
  ``SCAN_WORKSPACE_ROOT`` (default: the bundled ``ecdat_core/tests/fixtures``
  directory) — arbitrary path reads are rejected via :func:`validate_local_path`.

Public API:
    - :func:`ingest_local_directory` – walk a directory tree, yield source files.
    - :func:`validate_local_path` – enforce the local-path scan sandbox.
    - :func:`ingest_git_url` – shallow-clone a Git repository, return local path.
    - :func:`validate_git_url` – enforce the git-URL SSRF protections.
    - :func:`ingest_manifest_dependencies` – extract dependency info from manifests.
"""

from __future__ import annotations

import ipaddress
import os
import re
import shutil
import socket
import subprocess
import tempfile
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import urlparse

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

# Security policy configuration.  All read from the environment at call time
# so tests can override per-test; see AGENTS.md "Security Conventions".
_ENV_WORKSPACE_ROOT = "SCAN_WORKSPACE_ROOT"
_ENV_ALLOWED_HOSTS = "GIT_URL_ALLOWED_HOSTS"
_ENV_MAX_SIZE_MB = "GIT_URL_MAX_SIZE_MB"

# Default sandbox root: the bundled demo/showcase fixtures live here, so the
# existing fixture-based scans keep working with zero configuration.
_DEFAULT_WORKSPACE_ROOT = Path(__file__).resolve().parent / "tests" / "fixtures"

# Default post-clone repo size ceiling (MB) when GIT_URL_MAX_SIZE_MB is unset
# or invalid — a few hundred MB.
_DEFAULT_MAX_REPO_SIZE_MB = 200


# ---------------------------------------------------------------------------
# Local-path scan sandbox
# ---------------------------------------------------------------------------


def _resolve_workspace_root() -> Path:
    """Return the realpath of ``SCAN_WORKSPACE_ROOT`` (default: bundled fixtures).

    Reads ``SCAN_WORKSPACE_ROOT`` from the environment at call time; when unset,
    falls back to :data:`_DEFAULT_WORKSPACE_ROOT` (the directory holding the
    ``demo_repo`` / ``showcase_repo`` fixtures), so existing scans keep working
    with zero configuration.
    """
    configured = os.getenv(_ENV_WORKSPACE_ROOT)
    if configured:
        return Path(configured).resolve()
    return _DEFAULT_WORKSPACE_ROOT.resolve()


def _is_within(root: Path, candidate: Path) -> bool:
    """Return whether *candidate* equals *root* or is nested inside it."""
    return candidate == root or root in candidate.parents


def validate_local_path(path: str) -> str:
    """Validate that *path* resolves inside ``SCAN_WORKSPACE_ROOT``.

    Resolves symlinks via :func:`os.path.realpath` and rejects any path whose
    resolved location is not inside the configured workspace root.  This closes
    the arbitrary-path-read hole (e.g. submitting ``/etc`` or ``/app/backend``
    as a scan target) while keeping the bundled fixture scans working.

    Args:
        path: The local path a scan request asks to read.

    Returns:
        The resolved absolute path when *path* is inside the workspace.

    Raises:
        ValueError: If *path* resolves outside ``SCAN_WORKSPACE_ROOT``.
    """
    resolved = Path(path).resolve()
    root = _resolve_workspace_root()
    if not _is_within(root, resolved):
        raise ValueError(
            f"Path {path!r} is outside SCAN_WORKSPACE_ROOT ({root}). "
            "Only paths inside the configured scan workspace may be scanned."
        )
    return str(resolved)


# ---------------------------------------------------------------------------
# Git URL SSRF protection
# ---------------------------------------------------------------------------


def _allowed_git_hosts() -> frozenset[str]:
    """Parse the ``GIT_URL_ALLOWED_HOSTS`` allowlist from the environment.

    Returns an empty frozenset when the variable is unset (no restriction).
    Entries are comma-separated, trimmed, lowercased, and empties dropped.
    """
    raw = os.getenv(_ENV_ALLOWED_HOSTS, "")
    return frozenset(part.strip().lower() for part in raw.split(",") if part.strip())


def validate_git_url(git_url: str) -> None:
    """Reject git URLs that could target non-public (internal) network hosts.

    Enforced before any ``git clone`` is attempted:

    1. Scheme must be ``https://`` — ``file://``, ``git://``, ``ssh://``,
       plain ``http://`` and scheme-less strings are rejected.
    2. When ``GIT_URL_ALLOWED_HOSTS`` is set (comma-separated hostnames), the
       URL's hostname must be listed.  Unset = no allowlist restriction.
    3. Every address the hostname resolves to via :func:`socket.getaddrinfo`
       must be a public address — any resolved address flagged by the
       :mod:`ipaddress` module as private, loopback, link-local, reserved, or
       multicast rejects the URL.  This blocks internal networks, loopback,
       and cloud metadata endpoints such as ``169.254.169.254``.

    .. note::
        This is a resolve-then-connect check and does not defend against
        DNS-rebinding (the hostname could resolve differently between this
        check and the actual clone).  That TOCTOU window is a known,
        accepted residual risk at this stage.

    Args:
        git_url: The repository URL to validate.

    Raises:
        ValueError: With a clear message describing the specific rejection.
    """
    parsed = urlparse(git_url)
    if parsed.scheme.lower() != "https":
        raise ValueError(
            "Only https:// git URLs are allowed; got scheme "
            f"{parsed.scheme or '(none)'!r} for {git_url!r}"
        )

    hostname = parsed.hostname
    if not hostname:
        raise ValueError(f"Git URL {git_url!r} has no hostname")
    hostname = hostname.lower()

    allowlist = _allowed_git_hosts()
    if allowlist and hostname not in allowlist:
        raise ValueError(
            f"Host {hostname!r} is not in the GIT_URL_ALLOWED_HOSTS allowlist"
        )

    try:
        resolved = socket.getaddrinfo(hostname, 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise ValueError(
            f"Could not resolve host {hostname!r} for git URL {git_url!r}: {exc}"
        ) from exc

    for addr in resolved:
        ip_str = addr[4][0].split("%", 1)[0]  # strip IPv6 scope ids
        ip = ipaddress.ip_address(ip_str)
        # Check the embedded IPv4 for IPv4-mapped IPv6 (::ffff:a.b.c.d).
        probe = ip
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
            probe = ip.ipv4_mapped
        if (
            probe.is_private
            or probe.is_loopback
            or probe.is_link_local
            or probe.is_reserved
            or probe.is_multicast
        ):
            raise ValueError(
                f"Git URL host {hostname!r} resolves to non-public address "
                f"{ip_str}; refusing to clone an internal/private target"
            )


def _dir_size(root: Path) -> int:
    """Return the total size in bytes of every file under *root*."""
    total = 0
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            try:
                total += os.path.getsize(os.path.join(dirpath, name))
            except OSError:
                continue
    return total


def _max_repo_size_bytes() -> int:
    """Return the ``GIT_URL_MAX_SIZE_MB`` ceiling in bytes (default 200 MB)."""
    try:
        mb = int(os.getenv(_ENV_MAX_SIZE_MB, ""))
    except ValueError:
        mb = _DEFAULT_MAX_REPO_SIZE_MB
    if mb <= 0:
        mb = _DEFAULT_MAX_REPO_SIZE_MB
    return mb * 1024 * 1024


def ingest_local_directory(
    path: str, *, sandboxed: bool = True
) -> Iterator[tuple[str, str, str]]:
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
        sandboxed: When ``True`` (default) *path* must resolve inside
            ``SCAN_WORKSPACE_ROOT`` (see :func:`validate_local_path`).  Pass
            ``False`` only for scanner-created temporary clone directories
            (see :func:`~ecdat_core.cli.run_scan`) — never for user-supplied
            paths.

    Yields:
        Tuples of ``(file_path, content, language)`` for each successfully
        read source file.

    Raises:
        FileNotFoundError: If *path* does not exist or is not a directory.
        ValueError: If ``sandboxed`` and *path* resolves outside
            ``SCAN_WORKSPACE_ROOT``.
    """
    root = Path(path)
    if not root.is_dir():
        raise FileNotFoundError(f"Not a directory: {path}")
    if sandboxed:
        validate_local_path(path)

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
        ValueError: If *git_url* fails :func:`validate_git_url` (non-https
            scheme, non-public resolved address, or not on the
            ``GIT_URL_ALLOWED_HOSTS`` allowlist).
        RuntimeError: If the ``git clone`` command fails.  The exception
            message contains the stderr output from Git.  Also raised when
            the cloned repository exceeds the ``GIT_URL_MAX_SIZE_MB`` size
            ceiling (the temporary clone directory is removed first).
        subprocess.TimeoutExpired: If the clone exceeds 60 seconds.
    """
    validate_git_url(git_url)

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

    # Enforce the post-clone size ceiling so an oversized repository cannot
    # consume resources or hang the scan.
    size = _dir_size(Path(target_dir))
    limit = _max_repo_size_bytes()
    if size > limit:
        if workdir is None:
            shutil.rmtree(target_dir, ignore_errors=True)
        raise RuntimeError(
            f"Repository {git_url!r} is {size:,} bytes ({size // (1024 * 1024)} MB), "
            f"exceeding the GIT_URL_MAX_SIZE_MB ceiling of "
            f"{limit // (1024 * 1024)} MB; aborting scan"
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

    Raises:
        FileNotFoundError: If *path* does not exist or is not a directory.
        ValueError: If *path* resolves outside ``SCAN_WORKSPACE_ROOT``.
    """
    root = Path(path)
    if not root.is_dir():
        raise FileNotFoundError(f"Not a directory: {path}")
    validate_local_path(path)

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
