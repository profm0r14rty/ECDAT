"""Real-world ingestion hardening tests for ECDAT.

Exercises the new ingestion hardening features added in Phase 60/61:
pyvenv.cfg detection, extra skip dirs, binary detection, symlink safety,
and the ``exclude`` fnmatch filtering.
"""

from __future__ import annotations

import os
import pathlib

import pytest

from ecdat_core.ingestion import ingest_local_directory


@pytest.fixture(autouse=True)
def _scan_workspace(monkeypatch, tmp_path: object) -> None:
    """Sandbox local-path scans to this test's ``tmp_path``."""
    monkeypatch.setenv("SCAN_WORKSPACE_ROOT", str(pathlib.Path(tmp_path)))


# ---------------------------------------------------------------------------
# ≥ 8 tests
# ---------------------------------------------------------------------------


def test_node_modules_ignored(tmp_path: pathlib.Path) -> None:
    """Files inside node_modules/ must not appear."""
    nm = tmp_path / "node_modules" / "some-pkg"
    nm.mkdir(parents=True)
    (nm / "index.js").write_text("console.log(1);\n", encoding="utf-8")
    (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")

    results = list(ingest_local_directory(str(tmp_path), sandboxed=False))
    paths = [r[0] for r in results]
    basenames = {os.path.basename(p) for p in paths}
    assert basenames == {"app.py"}


def test_pyvenv_cfg_dir_ignored(tmp_path: pathlib.Path) -> None:
    """A directory containing pyvenv.cfg must be skipped entirely."""
    custom_venv = tmp_path / "custom_env"
    custom_venv.mkdir()
    (custom_venv / "pyvenv.cfg").write_text("home = ...\n", encoding="utf-8")
    (custom_venv / "helper.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "app.py").write_text("y = 2\n", encoding="utf-8")

    results = list(ingest_local_directory(str(tmp_path), sandboxed=False))
    paths = [r[0] for r in results]
    assert not any("custom_env" in p for p in paths)
    assert any(p.endswith("app.py") for p in paths)


def test_src_ok_py_found(tmp_path: pathlib.Path) -> None:
    """A normal .py file inside src/ must be found."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "ok.py").write_text("def foo(): pass\n", encoding="utf-8")

    results = list(ingest_local_directory(str(tmp_path), sandboxed=False))
    paths = [r[0] for r in results]
    assert any(p.endswith("ok.py") for p in paths)


def test_oversized_file_skipped(tmp_path: pathlib.Path) -> None:
    """Files > 2 MB must be skipped without error."""
    big = tmp_path / "big.py"
    big.write_bytes(b"x" * (2 * 1024 * 1024 + 1))
    (tmp_path / "small.py").write_text("a = 1\n", encoding="utf-8")

    results = list(ingest_local_directory(str(tmp_path), sandboxed=False))
    paths = [r[0] for r in results]
    assert not any(p.endswith("big.py") for p in paths)
    assert any(p.endswith("small.py") for p in paths)


def test_binary_file_skipped(tmp_path: pathlib.Path) -> None:
    """A file with NUL bytes in its first 8192 bytes must be skipped."""
    binary = tmp_path / "binary_image.py"
    binary.write_bytes(b"#!/usr/bin/env python3\n" + b"\x00" * 10)
    (tmp_path / "clean.py").write_text("x = 1\n", encoding="utf-8")

    results = list(ingest_local_directory(str(tmp_path), sandboxed=False))
    paths = [r[0] for r in results]
    assert not any(p.endswith("binary_image.py") for p in paths)
    assert any(p.endswith("clean.py") for p in paths)


def test_outside_root_symlink_not_followed(tmp_path: pathlib.Path) -> None:
    """A symlink resolving outside the scan root must be skipped."""
    if not hasattr(os, "symlink"):
        pytest.skip("symlink not available on this platform")

    inner = tmp_path / "inside"
    inner.mkdir()
    outside = tmp_path / "outside_dir"
    outside.mkdir()
    (outside / "secret.py").write_text("SECRET_KEY = 'abc'\n", encoding="utf-8")
    (inner / "app.py").write_text("x = 1\n", encoding="utf-8")

    # Symlink inside -> outside
    os.symlink(str(outside), str(inner / "escape"))

    results = list(ingest_local_directory(str(inner), sandboxed=False))
    paths = [r[0] for r in results]
    assert any(p.endswith("app.py") for p in paths)
    assert not any("secret.py" in p for p in paths)


def test_exclude_globs_file(tmp_path: pathlib.Path) -> None:
    """Files matching an exclude glob must be skipped."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "tests").mkdir()
    (src / "tests" / "test_a.py").write_text("def test(): pass\n", encoding="utf-8")
    (src / "core.py").write_text("x = 1\n", encoding="utf-8")

    results = list(ingest_local_directory(
        str(src), sandboxed=False, exclude=["*test*"]
    ))
    basenames = {os.path.basename(r[0]) for r in results}
    assert basenames == {"core.py"}


def test_exclude_globs_directory(tmp_path: pathlib.Path) -> None:
    """A directory whose name matches an exclude glob must be pruned."""
    (tmp_path / "migrations").mkdir()
    (tmp_path / "migrations" / "001.py").write_text("run()\n", encoding="utf-8")
    (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")

    results = list(ingest_local_directory(
        str(tmp_path), sandboxed=False, exclude=["migrations"]
    ))
    paths = [r[0] for r in results]
    assert any(p.endswith("app.py") for p in paths)
    assert not any("migrations" in p for p in paths)


def test_exclude_globs_nested(tmp_path: pathlib.Path) -> None:
    """Exclude matching a directory name anywhere in the path."""
    src = tmp_path / "src"
    src.mkdir()
    deep = src / "a" / "tests" / "b"
    deep.mkdir(parents=True)
    (deep / "test_thing.py").write_text("def test(): pass\n", encoding="utf-8")
    (src / "util.py").write_text("y = 2\n", encoding="utf-8")

    results = list(ingest_local_directory(
        str(src), sandboxed=False, exclude=["*test*"]
    ))
    basenames = {os.path.basename(r[0]) for r in results}
    assert basenames == {"util.py"}


def test_utf8_replace_on_invalid_bytes(tmp_path: pathlib.Path) -> None:
    """A file with a lone invalid UTF-8 byte must be decoded with replacement chars."""
    mixed = tmp_path / "mixed.py"
    # Valid UTF-8 prefix + one isolated continuation byte (invalid).
    mixed.write_bytes(b"x = 'hello'\n" + b"\x80")
    (tmp_path / "clean.py").write_text("y = 1\n", encoding="utf-8")

    results = list(ingest_local_directory(str(tmp_path), sandboxed=False))
    paths = [r[0] for r in results]
    assert any(p.endswith("mixed.py") for p in paths)
    assert any(p.endswith("clean.py") for p in paths)
    # The mixed file content should contain replacement character
    mixed_content = [r[1] for r in results if r[0].endswith("mixed.py")][0]
    assert "\ufffd" in mixed_content


def test_extra_skip_dirs(tmp_path: pathlib.Path) -> None:
    """``.tox``, ``.nox``, ``.mypy_cache``, ``site-packages`` must be skipped."""
    for skip in (".tox", ".nox", ".mypy_cache", "site-packages", ".idea", ".vscode"):
        d = tmp_path / skip
        d.mkdir()
        (d / "code.py").write_text("skip\n", encoding="utf-8")
    (tmp_path / "real.py").write_text("keep\n", encoding="utf-8")

    results = list(ingest_local_directory(str(tmp_path), sandboxed=False))
    paths = [r[0] for r in results]
    assert len([p for p in paths if p.endswith("real.py")]) == 1
    for skip in (".tox", ".nox", ".mypy_cache", "site-packages", ".idea", ".vscode"):
        assert not any(skip in p for p in paths), f"{skip!r} was not skipped"