"""Scanner service — the only app-layer code that talks to the engine.

This module is the single gateway through which CLI commands and the TUI
invoke the scanner engine (:func:`ecdat_core.cli.run_scan`).  It classifies
target strings, performs scans, and wraps the raw engine result into a
:class:`ScanVM` view-model that renderers consume.

Two call styles are supported for :func:`perform_scan`:

- The original string style (``perform_scan("path", is_git_url=False,
  save_history=True, exclude=(...))``) used by the ``scan`` command.
- The classified-target style (``perform_scan(classify_target("path"))``)
  which returns a :class:`ScanOutcome` bundling the result, view-model, and
  elapsed time.

Public API:
    - :data:`STAGE_LABELS` — human-readable stage names for progress reporting.
    - :class:`ScanError` — user-facing error with exit code.
    - :class:`Target` — classified scan target (local path or git URL).
    - :func:`classify_target` — classify and validate a raw target string.
    - :class:`ScanOutcome` — the result of a scan operation.
    - :func:`perform_scan` — run a scan and return the outcome/result.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union
from urllib.parse import urlparse

from ecdat_core.cli import run_scan
from ecdat_core.models import ScanResult
from ecdat.services.viewmodel import ScanVM, build_scan_vm

# ---------------------------------------------------------------------------
# Stage labels — keys correspond to logical scan phases.
# ---------------------------------------------------------------------------

STAGE_LABELS: dict[str, str] = {
    "clone": "Cloning repository",
    "ingest": "Indexing files",
    "scan": "Scanning files",
    "detect": "Detecting cryptographic artefacts",
    "assess": "Assessing quantum risk",
    "recommend": "Generating recommendations",
    "assemble": "Assembling result",
    "done": "Complete",
}

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

_GIT_UNSUPPORTED_MSG = (
    "Only https:// Git URLs are supported for direct scanning. "
    "For other URL schemes, clone the repository yourself and scan "
    "the local folder instead."
)


class ScanError(Exception):
    """A user-facing scan error with an exit code.

    Attributes:
        user_message: Human-readable error description.
        exit_code: Process exit code (2 = usage/validation, 3 = runtime).
        hint: Optional remediation hint, e.g. "Try cloning the repo manually."
    """

    def __init__(
        self,
        user_message: str,
        *,
        exit_code: int = 3,
        hint: Optional[str] = None,
    ) -> None:
        super().__init__(user_message)
        self.user_message = user_message
        self.exit_code = exit_code
        self.hint = hint


# ---------------------------------------------------------------------------
# Target classification
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Target:
    """A classified and validated scan target."""

    __slots__ = ("kind", "value", "display")

    kind: str  # "local" or "git"
    value: str  # Resolved path or URL
    display: str  # Original user-facing label


def classify_target(
    raw: str,
    *,
    force_git: bool = False,
) -> Target:
    """Classify a raw target string as a local path or git URL.

    Args:
        raw: The raw target string from user input (may have leading/trailing
            whitespace).
        force_git: When ``True``, treat *raw* as a git URL regardless of its
            format.

    Returns:
        A :class:`Target` with kind, resolved value, and display label.

    Raises:
        ScanError: exit_code=2 for invalid or unsupported targets (empty
            string, unsupported URL scheme, non-existent path, file-not-dir).
    """
    raw = raw.strip()
    if not raw:
        raise ScanError(
            "No scan target provided. Specify a local directory path or a "
            "https:// Git URL.",
            exit_code=2,
            hint="Usage: ecdat scan <path-or-url>",
        )

    if force_git:
        return _classify_git(raw)

    # Heuristic: if it looks like a URL (has "://") or an scp-style git
    # address ("git@host:…"), classify as git.  Windows drive paths (C:\\…)
    # and plain relative/absolute paths fall through to local.
    if "://" in raw or raw.startswith("git@"):
        return _classify_git(raw)

    return _classify_local(raw)


def _classify_git(raw: str) -> Target:
    """Classify and validate a git URL target.

    Only ``https://`` URLs are accepted.  Everything else — ``http://``,
    ``ssh://``, ``git://``, ``file://``, ``git@…`` scp-style — is rejected
    with exit code 2.
    """
    # git@ scp-style
    if raw.startswith("git@"):
        raise ScanError(
            _GIT_UNSUPPORTED_MSG,
            exit_code=2,
            hint=f"Try: git clone {raw} && ecdat scan <repo-dir>",
        )

    parsed = urlparse(raw)
    scheme = parsed.scheme.lower()

    if scheme == "https":
        return Target(kind="git", value=raw, display=raw)

    # Anything else with a scheme or weird format — reject.
    raise ScanError(
        _GIT_UNSUPPORTED_MSG,
        exit_code=2,
        hint=f"Try: git clone {raw} && ecdat scan <repo-dir>",
    )


def _classify_local(raw: str) -> Target:
    """Classify and validate a local directory path target."""
    path = Path(raw).expanduser().resolve()

    if not path.exists():
        raise ScanError(
            f"Path does not exist: {raw}",
            exit_code=2,
        )

    if not path.is_dir():
        raise ScanError(
            f"Not a directory: {raw}",
            exit_code=2,
            hint="Specify a directory to scan, not a single file.",
        )

    return Target(kind="local", value=str(path), display=raw)


# ---------------------------------------------------------------------------
# Scan execution
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ScanOutcome:
    """The result of a scan operation.

    Attributes:
        result: The raw engine ``ScanResult`` returned by ``run_scan``.
        vm: The renderer-ready :class:`ScanVM` view-model.
        duration_s: Wall-clock scan duration in seconds.
    """

    __slots__ = ("result", "vm", "duration_s")

    result: ScanResult
    vm: ScanVM
    duration_s: float


def _run_engine(
    target: Target,
    *,
    exclude: Sequence[str] = (),
    on_progress=None,
) -> ScanResult:
    """Invoke the engine for *target*, mapping failures to :class:`ScanError`.

    Optional keyword arguments are only forwarded when set, so the call for a
    plain scan is exactly ``run_scan(path, sandboxed=False)`` (git:
    ``run_scan(url, is_git_url=True)``).
    """
    extra: dict = {}
    if exclude:
        extra["exclude"] = exclude
    if on_progress is not None:
        extra["on_progress"] = on_progress

    try:
        if target.kind == "git":
            return run_scan(target.value, is_git_url=True, **extra)
        # CLI/TUI scans treat the invoking user as the trust boundary.
        return run_scan(target.value, sandboxed=False, **extra)
    except ScanError:
        raise
    except ValueError as exc:
        # Engine validation errors from git-URL checks (validate_git_url in
        # ingestion.py raises ValueError) — these are usage errors.
        raise ScanError(str(exc), exit_code=2) from exc
    except KeyboardInterrupt:
        raise
    except Exception as exc:
        raise ScanError(
            f"Scan failed: {type(exc).__name__}: {exc}",
            exit_code=3,
        ) from exc


def perform_scan(
    target: Union[str, Target],
    *,
    is_git_url: bool = False,
    save_history: bool = True,
    exclude: Sequence[str] = (),
    force_git: bool = False,
    label: Optional[str] = None,
    on_progress=None,
) -> Union[ScanResult, ScanOutcome]:
    """Run an ECDAT scan against *target*.

    Two call styles are supported:

    - **String style** (``ecdat scan``): pass a raw path/URL string and the
      result is a :class:`~ecdat_core.models.ScanResult`; with
      ``save_history=True`` the result is persisted best-effort.
    - **Classified style** (``ecdat demo``, the TUI): pass a :class:`Target`
      from :func:`classify_target` and the result is a :class:`ScanOutcome`
      wrapping the engine result, the :class:`ScanVM`, and the duration.

    Args:
        target: A raw path/URL string, or a classified :class:`Target`.
        is_git_url: (string style) Treat *target* as a git URL.
        save_history: (string style) Persist the result to scan history.
        exclude: ``fnmatch`` patterns passed to the scanner.
        force_git: Unused — retained for signature compatibility.
        label: (classified style) Display label for the scan VM.
        on_progress: Optional engine progress callback.

    Returns:
        A :class:`ScanResult` for the string style, or a :class:`ScanOutcome`
        for the classified style.

    Raises:
        ScanError: exit_code=2 for git-URL/validation errors, 3 for runtime
            failures.
    """
    if isinstance(target, Target):
        start = time.monotonic()
        result = _run_engine(target, exclude=exclude, on_progress=on_progress)
        duration_s = time.monotonic() - start
        vm = build_scan_vm(
            result, target=label or target.display, duration_s=duration_s
        )
        return ScanOutcome(result=result, vm=vm, duration_s=duration_s)

    # --- string style -----------------------------------------------------
    classified = classify_target(target, force_git=is_git_url)
    result = _run_engine(classified, exclude=exclude, on_progress=on_progress)

    if save_history:
        try:
            from ecdat.services.history import save_scan as _history_save

            _history_save(result)
        except Exception:
            # History save never fails a scan.
            pass

    return result
