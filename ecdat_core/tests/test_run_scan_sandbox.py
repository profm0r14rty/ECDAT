"""Tests for ``run_scan``'s ``sandboxed`` keyword (Phase 59).

The pip-installed ``ecdat`` CLI treats the invoking user as the trust
boundary and therefore calls :func:`~ecdat_core.cli.run_scan` with
``sandboxed=False``; the HTTP API keeps the workspace sandbox.  These tests
pin both behaviours: the opt-out works, and the default (sandboxed) is
unchanged so existing callers — including the FastAPI backend — are
unaffected.

Every test clears ``SCAN_WORKSPACE_ROOT`` so the package-relative default
root (``ecdat_core/tests/fixtures``) is used; the scanner-created ``tmp_path``
directory is guaranteed to fall outside it.
"""

from __future__ import annotations

import pytest

from ecdat_core.cli import run_scan
from ecdat_core.models import ScanResult

# A minimal file the detector recognises as a cryptographic artefact: MD5 is
# a classically-broken hash covered by signatures.json, so a scan of this file
# yields at least one detection.
_CRYPTO_PY = 'import hashlib\n\nhashlib.md5(b"x")\n'


def _write_crypto_file(root) -> None:
    """Write one detectable Python file into *root*."""
    (root / "sample.py").write_text(_CRYPTO_PY, encoding="utf-8")


def test_local_scan_is_rejected_while_sandboxed(tmp_path, monkeypatch):
    """(a) A local path outside the workspace is rejected by the sandbox."""
    monkeypatch.delenv("SCAN_WORKSPACE_ROOT", raising=False)
    _write_crypto_file(tmp_path)

    with pytest.raises(ValueError):
        run_scan(str(tmp_path))


def test_local_scan_can_opt_out_of_sandbox(tmp_path, monkeypatch):
    """(b) ``sandboxed=False`` lets an arbitrary local path scan and detect."""
    monkeypatch.delenv("SCAN_WORKSPACE_ROOT", raising=False)
    _write_crypto_file(tmp_path)

    result = run_scan(str(tmp_path), sandboxed=False)

    assert isinstance(result, ScanResult)
    assert len(result.detections) >= 1


def test_sandbox_default_is_unchanged(tmp_path, monkeypatch):
    """(c) Omitting ``sandboxed`` keeps the old (sandboxed) behaviour."""
    monkeypatch.delenv("SCAN_WORKSPACE_ROOT", raising=False)
    _write_crypto_file(tmp_path)

    with pytest.raises(ValueError):
        run_scan(str(tmp_path))
