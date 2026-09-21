"""Packaging integrity tests — verify what ships in wheel and sdist.

Builds the wheel+sdist ONCE (session-scoped fixture), then inspects every
artefact: wheel member list, METADATA, entry points, markdown link hygiene,
sdist contents, and ``twine check``.  A network-gated test installs the
built wheel into a fresh venv and exercises the console script end-to-end.

Every test in this module carries ``@pytest.mark.packaging``.  Run them
explicitly with ``-m packaging``; the default suite deselects only the
``network`` marker, so packaging tests do run under a plain ``pytest`` too.
The venv install smoke test is also marked ``network`` and is therefore
deselected unless explicitly opted in.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tarfile
import venv
import zipfile
from dataclasses import dataclass
from email.parser import HeaderParser
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _wheel_members(wheel_path: Path) -> List[str]:
    """Return sorted member names from a wheel."""
    with zipfile.ZipFile(str(wheel_path), "r") as zf:
        return sorted(zf.namelist())


def _wheel_total_size(wheel_path: Path) -> int:
    """Return the sum of ``file_size`` for every member in the wheel."""
    with zipfile.ZipFile(str(wheel_path), "r") as zf:
        return sum(info.file_size for info in zf.infolist())


def _read_metadata(wheel_path: Path) -> Tuple[str, str]:
    """Return ``(raw_headers, body)`` from ``*.dist-info/METADATA`` inside
    the wheel.

    Headers end at the first blank line; everything after it is the long
    description body.  Both are returned as plain strings.
    """
    members = _wheel_members(wheel_path)
    metadata_names = [m for m in members if m.endswith(".dist-info/METADATA")]
    if not metadata_names:
        raise FileNotFoundError("No .dist-info/METADATA found in wheel")
    with zipfile.ZipFile(str(wheel_path), "r") as zf:
        raw = zf.read(metadata_names[0]).decode("utf-8")
    parts = raw.split("\n\n", 1)
    headers = parts[0]
    body = parts[1] if len(parts) > 1 else ""
    return headers, body


def _parse_metadata_headers(raw_headers: str) -> Dict[str, str]:
    """Parse RFC 822-style headers into a ``{Name: value}`` dict."""
    parser = HeaderParser()
    msg = parser.parsestr(raw_headers)
    return dict(msg)


def _get_all_requires_dist(wheel_path: Path) -> List[str]:
    headers, _body = _read_metadata(wheel_path)
    entries: List[str] = []
    for line in headers.splitlines():
        if line.startswith("Requires-Dist:"):
            entries.append(line.split(":", 1)[1].strip())
    return entries


def _read_entry_points(wheel_path: Path) -> Optional[str]:
    """Read ``*.dist-info/entry_points.txt``, or return ``None``."""
    members = _wheel_members(wheel_path)
    ep_names = [m for m in members if m.endswith(".dist-info/entry_points.txt")]
    if not ep_names:
        return None
    with zipfile.ZipFile(str(wheel_path), "r") as zf:
        return zf.read(ep_names[0]).decode("utf-8")


def _extract_sdist_members(sdist_path: Path) -> List[str]:
    """Return a sorted list of member names in the source tarball."""
    with tarfile.open(str(sdist_path), "r:gz") as tf:
        return sorted(tf.getnames())


# ---------------------------------------------------------------------------
# Shared fixture — build once per session
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BuiltDist:
    """Result of a single ``python -m build`` run."""

    dist_dir: Path
    wheel: Path
    sdist: Path


@pytest.fixture(scope="session")
def built_dist(tmp_path_factory: pytest.TempPathFactory) -> BuiltDist:
    """Build the wheel and sdist once for the whole test session.

    Skips the session if ``build`` is not installed (dev dependency).
    """
    try:
        import build  # noqa: F401
    except ImportError:
        pytest.skip("the `build` package is not installed")

    dist_dir = tmp_path_factory.mktemp("dist")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "build",
            "--outdir",
            str(dist_dir),
            ".",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=600,
        cwd=str(_REPO_ROOT),
    )

    # If the build failed, surface stderr in the assertion message.
    assert result.returncode == 0, (
        f"Build failed (exit {result.returncode})\n"
        f"STDERR:\n{result.stderr}\n"
        f"STDOUT:\n{result.stdout}"
    )

    wheels = sorted(dist_dir.glob("*.whl"))
    sdists = sorted(dist_dir.glob("*.tar.gz"))

    assert len(wheels) == 1, f"Expected exactly 1 wheel, got {len(wheels)}: {wheels}"
    assert len(sdists) == 1, f"Expected exactly 1 sdist, got {len(sdists)}: {sdists}"

    return BuiltDist(dist_dir=dist_dir, wheel=wheels[0], sdist=sdists[0])


# ===========================================================================
# Wheel member tests
# ===========================================================================


class TestWheelContents:
    """Verify the files that ship inside the wheel."""

    @pytest.mark.packaging
    def test_contains_required_package_files(self, built_dist: BuiltDist) -> None:
        """The wheel must include the minimal package surfaces."""
        members = _wheel_members(built_dist.wheel)
        required = {
            "ecdat/__init__.py",
            "ecdat/py.typed",
            "ecdat/cli/__init__.py",
            "ecdat_core/signatures.json",
        }
        missing = required - set(members)
        assert not missing, f"Missing wheel members: {missing}"

    @pytest.mark.packaging
    def test_contains_demo_project(self, built_dist: BuiltDist) -> None:
        """The wheel must ship at least 8 demo_project files."""
        members = _wheel_members(built_dist.wheel)
        demo_members = [m for m in members if m.startswith("ecdat/demo_project/")]
        assert len(demo_members) >= 8, (
            f"Expected >= 8 demo_project members, got {len(demo_members)}: {demo_members}"
        )

    @pytest.mark.packaging
    def test_no_restricted_dirs_in_wheel(self, built_dist: BuiltDist) -> None:
        """The wheel must not leak backend, frontend, verification, tests,
        or monorepo housekeeping files."""
        members = _wheel_members(built_dist.wheel)
        forbidden_substrings = [
            "/tests/",
            "backend/",
            "frontend/",
            "verification/",
            ".aider",
            "AGENTS.md",
            "CONVENTIONS.md",
            "progress.md",
        ]

        violations: List[str] = []
        for member in members:
            for forbidden in forbidden_substrings:
                if forbidden in member:
                    violations.append(member)
                    break

        assert not violations, (
            f"Wheel contains forbidden paths: {violations}"
        )

    @pytest.mark.packaging
    def test_wheel_total_size_below_limit(self, built_dist: BuiltDist) -> None:
        """Total uncompressed size of all wheel members must be < 5 MB."""
        total = _wheel_total_size(built_dist.wheel)
        limit = 5 * 1024 * 1024  # 5 MB
        assert total < limit, (
            f"Wheel uncompressed size {total:,} bytes exceeds {limit:,} bytes limit"
        )


# ===========================================================================
# Metadata tests
# ===========================================================================


class TestWheelMetadata:
    """Inspect the ``*.dist-info/METADATA`` and ``entry_points.txt``."""

    @pytest.mark.packaging
    def test_name_is_ecdat(self, built_dist: BuiltDist) -> None:
        headers, _body = _read_metadata(built_dist.wheel)
        parsed = _parse_metadata_headers(headers)
        assert parsed.get("Name") == "ecdat", f"Expected Name: ecdat, got {parsed.get('Name')!r}"

    @pytest.mark.packaging
    def test_requires_python_present(self, built_dist: BuiltDist) -> None:
        headers, _body = _read_metadata(built_dist.wheel)
        parsed = _parse_metadata_headers(headers)
        rp = parsed.get("Requires-Python", "")
        assert rp, "Requires-Python header is missing or empty"

    @pytest.mark.packaging
    def test_requires_dist_includes_pydantic(self, built_dist: BuiltDist) -> None:
        entries = _get_all_requires_dist(built_dist.wheel)
        assert entries, "No Requires-Dist header at all"
        pydantic_entries = [v for v in entries if "pydantic" in v]
        assert pydantic_entries, (
            f"No Requires-Dist line mentioning pydantic. All: {entries}"
        )

    @pytest.mark.packaging
    def test_requires_dist_includes_rich(self, built_dist: BuiltDist) -> None:
        entries = _get_all_requires_dist(built_dist.wheel)
        rich_entries = [v for v in entries if "rich" in v]
        assert rich_entries, (
            f"No Requires-Dist line mentioning rich. All: {entries}"
        )

    @pytest.mark.packaging
    def test_entry_point_console_script(self, built_dist: BuiltDist) -> None:
        ep_text = _read_entry_points(built_dist.wheel)
        assert ep_text is not None, "entry_points.txt not found in wheel"
        expected = "ecdat = ecdat.cli:main"
        found = False
        in_console = False
        for line in ep_text.splitlines():
            line = line.strip()
            if line == "[console_scripts]":
                in_console = True
            elif line.startswith("[") and in_console:
                in_console = False
            elif in_console and line:
                if "ecdat" in line:
                    assert expected in line or line == expected, (
                        f"Expected entry point {expected!r}, got {line!r}"
                    )
                    found = True
                    break
        assert found, f"Entry point {expected!r} not found in entry_points.txt:\n{ep_text}"

    @pytest.mark.packaging
    def test_long_description_no_relative_markdown_links(self, built_dist: BuiltDist) -> None:
        """STRICT: the long description body must contain NO relative markdown links.

        A link target is relative unless it starts with ``http://``,
        ``https://``, ``mailto:``, or ``#``.

        NOTE: This test is EXPECTED TO FAIL because ``PYPI_README.md``
        line ~94 currently contains ``[SECURITY.md](SECURITY.md)``, which
        is a relative link.  The assertion is kept faithful to the desired
        invariant; the pre-existing README bug is not covered by this
        task's scope.
        """
        _, body = _read_metadata(built_dist.wheel)
        # Find all markdown link targets: [text](target)
        targets = re.findall(r"\]\(([^)]+)\)", body)
        relative: List[str] = []
        for target in targets:
            target = target.strip()
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            relative.append(target)
        assert not relative, (
            f"Long description contains relative markdown links: {relative}"
        )


# ===========================================================================
# Sdist tests
# ===========================================================================


class TestSdistContents:
    """Inspect the source distribution tarball."""

    @pytest.mark.packaging
    def test_sdist_has_top_level_dir(self, built_dist: BuiltDist) -> None:
        members = _extract_sdist_members(built_dist.sdist)
        assert members, "Sdist is empty"
        # Everything should be under a single top-level directory.
        prefixes = {m.split("/", 1)[0] for m in members}
        assert len(prefixes) == 0 or len(prefixes) == 1, (
            f"Sdist should have a single top-level dir, got: {prefixes}"
        )

    @pytest.mark.packaging
    def test_sdist_contains_essential_files(self, built_dist: BuiltDist) -> None:
        members = _extract_sdist_members(built_dist.sdist)
        # Strip the top-level dir so we can match filenames easily.
        stripped = _strip_sdist_prefix(members)
        required = {"LICENSE", "PYPI_README.md", "pyproject.toml"}
        missing = required - set(stripped)
        assert not missing, f"Sdist missing essential files: {missing}"

    @pytest.mark.packaging
    def test_sdist_contains_tests(self, built_dist: BuiltDist) -> None:
        members = _extract_sdist_members(built_dist.sdist)
        stripped = _strip_sdist_prefix(members)
        test_paths = [m for m in stripped if m.startswith("ecdat/tests/")]
        assert test_paths, "Sdist should contain at least one path under ecdat/tests/"

    @pytest.mark.packaging
    def test_sdist_excludes_restricted_areas(self, built_dist: BuiltDist) -> None:
        members = _extract_sdist_members(built_dist.sdist)
        forbidden = [
            "backend/",
            "frontend/",
            "verification/",
            "render.yaml",
            "docker-compose.yml",
            "AGENTS.md",
        ]
        violations: List[str] = []
        # For prefixed dirs like "backend/", check if any member starts
        # with the top-level-dir + "backend/".
        # For single-file names like "render.yaml", check if the stripped
        # portion equals that.
        stripped = _strip_sdist_prefix(members)

        for i, member in enumerate(members):
            s = stripped[i] if i < len(stripped) else member
            for fb in forbidden:
                if fb.endswith("/"):
                    # A directory prefix — check the full member path
                    # contains /backend/ (or similar) after the top dir.
                    if s.startswith(fb):
                        violations.append(member)
                        break
                else:
                    if s == fb:
                        violations.append(member)
                        break

        assert not violations, (
            f"Sdist contains restricted paths: {violations}"
        )

    @pytest.mark.packaging
    def test_sdist_excludes_ecdat_prefix_not_leaking(self, built_dist: BuiltDist) -> None:
        """The sdist ships ``ecdat/...``, ``ecdat_core/...``, and
        ``ecdat.egg-info/...`` — all are legitimate; nothing else should
        carry an ``ecdat`` prefix."""
        allowed = {"ecdat/", "ecdat_core/", "ecdat.egg-info/"}
        members = _extract_sdist_members(built_dist.sdist)
        stripped = _strip_sdist_prefix(members)
        for path in stripped:
            if path.endswith(".dev0") or "/" not in path:
                continue
            if path.startswith("ecdat"):
                ok = any(path.startswith(prefix) for prefix in allowed)
                assert ok, (
                    f"Path with 'ecdat' prefix outside allowed dirs: {path}"
                )


# ---------------------------------------------------------------------------
# Sdist helper — the sdist contains one top-level dir like ``ecdat-0.2.0.dev0/``
# followed by every path.  Strip that prefix for friendlier assertions.
# ---------------------------------------------------------------------------

def _sdist_top_dirs(members: List[str]) -> List[str]:
    """Return a list of top-level dir names from each sdist member."""
    return [m.split("/", 1)[0] for m in members if "/" in m]


def _strip_sdist_prefix(members: List[str]) -> List[str]:
    """Return member paths with the common top-level dir prefix removed.

    E.g. ``ecdat-0.2.0.dev0/ecdat/cli/__init__.py`` → ``ecdat/cli/__init__.py``.
    If no common prefix exists, returns members unchanged.
    """
    if not members:
        return []
    prefixes = _sdist_top_dirs(members)
    if not prefixes:
        return list(members)
    unique = set(prefixes)
    if len(unique) != 1:
        return list(members)
    prefix = prefixes[0] + "/"
    stripped = []
    for m in members:
        if m.startswith(prefix):
            stripped.append(m[len(prefix):])
        else:
            stripped.append(m)
    return stripped


# ===========================================================================
# Twine check
# ===========================================================================


@pytest.mark.packaging
def test_twine_check(built_dist: BuiltDist) -> None:
    """Run ``twine check`` on both the wheel and sdist.

    Skips if ``twine`` is not installed.
    """
    try:
        import twine  # noqa: F401
    except ImportError:
        pytest.skip("twine is not installed")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "twine",
            "check",
            str(built_dist.wheel),
            str(built_dist.sdist),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
    )
    assert result.returncode == 0, (
        f"twine check failed (exit {result.returncode})\n"
        f"STDOUT:{result.stdout}\n"
        f"STDERR:{result.stderr}"
    )


# ===========================================================================
# Fresh-venv install + smoke test (network-gated)
# ===========================================================================


@pytest.mark.packaging
@pytest.mark.network
def test_fresh_venv_install_and_cli(tmp_path: Path, built_dist: BuiltDist) -> None:
    """Create a fresh venv, install the built wheel, and exercise the CLI.

    This is the only test that reaches the network (``pip install``
    pulls dependencies from PyPI).
    """
    # 1. Create a fresh venv.
    venv_dir = tmp_path / "venv"
    venv.EnvBuilder(with_pip=True).create(str(venv_dir))

    # Resolve the venv's python and pip.
    venv_python = (
        venv_dir / ("Scripts" if sys.platform == "win32" else "bin") / "python"
    )
    venv_pip = (
        venv_dir / ("Scripts" if sys.platform == "win32" else "bin") / "pip"
    )

    # 2. Install the built wheel into the fresh venv.
    #    Use --force-reinstall in case setuptools/pip are already there.
    install_proc = subprocess.run(
        [str(venv_pip), "install", "--force-reinstall", str(built_dist.wheel)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=600,
    )
    assert install_proc.returncode == 0, (
        f"pip install failed (exit {install_proc.returncode})\n"
        f"STDERR:\n{install_proc.stderr}\n"
        f"STDOUT:\n{install_proc.stdout}"
    )

    # Resolve the console script.
    ecdat_bin = venv_dir / ("Scripts" if sys.platform == "win32" else "bin") / "ecdat"

    # 3. Run from a DIFFERENT cwd (outside the repo) so the tests prove the
    #    installed package works, not the source checkout.
    work_dir = tmp_path / "workdir"
    work_dir.mkdir()

    # 3a. --version
    version_proc = subprocess.run(
        [str(ecdat_bin), "--version"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        cwd=str(work_dir),
    )
    assert version_proc.returncode == 0, (
        f"ecdat --version failed (exit {version_proc.returncode})\n"
        f"STDERR:\n{version_proc.stderr}"
    )
    assert "ecdat" in version_proc.stdout, (
        f"ecdat --version output missing expected text: {version_proc.stdout!r}"
    )

    # 3b. doctor
    doctor_proc = subprocess.run(
        [str(ecdat_bin), "doctor"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        cwd=str(work_dir),
    )
    assert doctor_proc.returncode == 0, (
        f"ecdat doctor failed (exit {doctor_proc.returncode})\n"
        f"STDERR:\n{doctor_proc.stderr}\n"
        f"STDOUT:\n{doctor_proc.stdout}"
    )

    # 3c. demo -f json
    demo_proc = subprocess.run(
        [str(ecdat_bin), "demo", "-f", "json"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        cwd=str(work_dir),
    )
    assert demo_proc.returncode == 0, (
        f"ecdat demo -f json failed (exit {demo_proc.returncode})\n"
        f"STDERR:\n{demo_proc.stderr}\n"
        f"STDOUT:\n{demo_proc.stdout}"
    )
    demo_json = json.loads(demo_proc.stdout)
    assert isinstance(demo_json, dict), "demo -f json output is not a JSON object"

    # 3d. scan a temp folder with a crypto-using file
    scan_dir = tmp_path / "scandir"
    scan_dir.mkdir()
    py_file = scan_dir / "test_crypto.py"
    py_file.write_text("import hashlib\nhashlib.md5(b'x')\n", encoding="utf-8")

    scan_proc = subprocess.run(
        [str(ecdat_bin), "scan", str(scan_dir), "-f", "json"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        cwd=str(work_dir),
    )
    assert scan_proc.returncode == 0, (
        f"ecdat scan -f json failed (exit {scan_proc.returncode})\n"
        f"STDERR:\n{scan_proc.stderr}\n"
        f"STDOUT:\n{scan_proc.stdout}"
    )
    scan_json = json.loads(scan_proc.stdout)
    detections = scan_json.get("detections", [])
    assert isinstance(detections, list)
    assert len(detections) >= 1, (
        f"Expected at least 1 detection for MD5 usage, got {len(detections)}"
    )