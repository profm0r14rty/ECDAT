"""Tests for ECDAT ingestion: directory walking, manifest extraction, Git clone.

Uses :mod:`pytest` ``tmp_path`` fixtures to build small directory trees on the
fly so no network or real repositories are required (except the clone tests
which are marked with ``@pytest.mark.network``).

The module-scoped autouse fixture below sandboxes local-path ingestion to each
test's ``tmp_path`` by setting ``SCAN_WORKSPACE_ROOT`` (Phase 45 security
convention); the sandbox tests themselves override it explicitly.
"""

from __future__ import annotations

import json
import os
import textwrap

import pytest

from ecdat_core.ingestion import (
    ingest_git_url,
    ingest_local_directory,
    ingest_manifest_dependencies,
    validate_git_url,
    validate_local_path,
)


@pytest.fixture(autouse=True)
def _scan_workspace(monkeypatch, tmp_path: object) -> None:
    """Sandbox local-path scans to this test's ``tmp_path``.

    Phase 45 requires every local-path scan to resolve inside
    ``SCAN_WORKSPACE_ROOT``; the existing tmp_path-based tests create their
    trees inside pytest's temp dir, so pin the workspace root there.  Tests
    that exercise the sandbox itself override the variable explicitly.

    Scoped to this module only (defined here, not in conftest) so tests in
    other modules — e.g. ``test_end_to_end.py`` scanning ``demo_repo`` — still
    use the default workspace root (the bundled fixtures directory) unchanged.
    """
    import pathlib

    monkeypatch.setenv("SCAN_WORKSPACE_ROOT", str(pathlib.Path(tmp_path)))


# ---------------------------------------------------------------------------
# ingest_local_directory
# ---------------------------------------------------------------------------


class TestIngestLocalDirectory:
    """Walk a temp directory, verify skipped dirs and file yielded correctly."""

    def test_yields_supported_files(self, tmp_path: object) -> None:
        """A .py file should be yielded with correct content and language."""
        import pathlib

        root = pathlib.Path(tmp_path)  # type: ignore[arg-type]
        src = root / "app.py"
        src.write_text("x = 1\n", encoding="utf-8")

        results = list(ingest_local_directory(str(root)))
        assert len(results) == 1
        file_path, content, language = results[0]
        assert file_path == str(src)
        assert content == "x = 1\n"
        assert language == "python"

    def test_skips_node_modules(self, tmp_path: object) -> None:
        """Files inside ``node_modules/`` must not appear in the output."""
        import pathlib

        root = pathlib.Path(tmp_path)  # type: ignore[arg-type]
        nm_dir = root / "node_modules" / "some-pkg"
        nm_dir.mkdir(parents=True)
        (nm_dir / "index.js").write_text("var x;\n", encoding="utf-8")

        results = list(ingest_local_directory(str(root)))
        assert results == []

    def test_skips_hidden_and_build_dirs(self, tmp_path: object) -> None:
        """``.git``, ``__pycache__``, ``dist``, ``build`` are all skipped."""
        import pathlib

        root = pathlib.Path(tmp_path)  # type: ignore[arg-type]
        for dirname in (".git", "__pycache__", "dist", "build"):
            d = root / dirname
            d.mkdir()
            (d / "code.py").write_text("skip me\n", encoding="utf-8")

        results = list(ingest_local_directory(str(root)))
        assert results == []

    def test_skips_oversized_files(self, tmp_path: object) -> None:
        """Files over 2 MB are silently skipped."""
        import pathlib
        import os

        root = pathlib.Path(tmp_path)  # type: ignore[arg-type]
        big = root / "big.py"
        big.write_bytes(b"x" * (2 * 1024 * 1024 + 1))

        results = list(ingest_local_directory(str(root)))
        assert results == []

    def test_skips_non_utf8_files(self, tmp_path: object) -> None:
        """Binary files that fail UTF-8 decoding should be skipped, not crash."""
        import pathlib

        root = pathlib.Path(tmp_path)  # type: ignore[arg-type]
        bad = root / "binary.py"
        bad.write_bytes(b"\x80\x81\x82\x83\xfe\xff")

        results = list(ingest_local_directory(str(root)))
        assert results == []

    def test_skips_unsupported_extensions(self, tmp_path: object) -> None:
        """Files with unsupported extensions (e.g. .txt) are not yielded."""
        import pathlib

        root = pathlib.Path(tmp_path)  # type: ignore[arg-type]
        (root / "readme.txt").write_text("hello\n", encoding="utf-8")

        results = list(ingest_local_directory(str(root)))
        assert results == []

    def test_raises_on_nonexistent_path(self) -> None:
        with pytest.raises(FileNotFoundError):
            list(ingest_local_directory("/no/such/dir/ecdat_test_404"))

    def test_nested_skipped_dirs(self, tmp_path: object) -> None:
        """``venv/`` nested inside ``src/`` is still skipped."""
        import pathlib

        root = pathlib.Path(tmp_path)  # type: ignore[arg-type]
        nested = root / "src" / "venv" / "lib"
        nested.mkdir(parents=True)
        (nested / "helper.py").write_text("y = 2\n", encoding="utf-8")
        # Also put a valid file at root level so we get at least one yield.
        (root / "main.py").write_text("z = 3\n", encoding="utf-8")

        results = list(ingest_local_directory(str(root)))
        assert len(results) == 1
        assert results[0][0].endswith("main.py")


# ---------------------------------------------------------------------------
# ingest_manifest_dependencies
# ---------------------------------------------------------------------------


class TestIngestManifestDependencies:
    """Extract dependencies from various manifest formats in a temp tree."""

    def test_requirements_txt(self, tmp_path: object) -> None:
        """Parse name==version pairs from a requirements.txt."""
        import pathlib

        root = pathlib.Path(tmp_path)  # type: ignore[arg-type]
        req = root / "requirements.txt"
        req.write_text(
            textwrap.dedent("""\
                requests==2.31.0
                pydantic>=2.0
                click
                # comment line
                flask==2.3.2
            """),
            encoding="utf-8",
        )

        deps = ingest_manifest_dependencies(str(root))
        names = {d["name"] for d in deps}
        assert "requests" in names
        assert "flask" in names
        assert "pydantic" in names  # version spec kept as-is
        assert "click" in names
        # Check structure
        for d in deps:
            assert "name" in d
            assert "version" in d
            assert "manifest_file" in d

    def test_package_json(self, tmp_path: object) -> None:
        """Parse dependencies and devDependencies from package.json."""
        import pathlib

        root = pathlib.Path(tmp_path)  # type: ignore[arg-type]
        pkg = root / "package.json"
        pkg.write_text(
            json.dumps(
                {
                    "name": "my-app",
                    "dependencies": {"react": "^18.2.0", "lodash": "^4.17.21"},
                    "devDependencies": {"vitest": "^1.0.0"},
                }
            ),
            encoding="utf-8",
        )

        deps = ingest_manifest_dependencies(str(root))
        names = {d["name"] for d in deps}
        assert "react" in names
        assert "vitest" in names
        react_dep = next(d for d in deps if d["name"] == "react")
        assert react_dep["version"] == "^18.2.0"

    def test_go_mod(self, tmp_path: object) -> None:
        """Parse require blocks from go.mod."""
        import pathlib

        root = pathlib.Path(tmp_path)  # type: ignore[arg-type]
        gomod = root / "go.mod"
        gomod.write_text(
            textwrap.dedent("""\
                module example.com/foo

                go 1.21

                require (
                    github.com/gin-gonic/gin v1.9.1
                    github.com/go-yaml/yaml v2.4.0 // indirect
                )
            """),
            encoding="utf-8",
        )

        deps = ingest_manifest_dependencies(str(root))
        names = {d["name"] for d in deps}
        assert "github.com/gin-gonic/gin" in names
        assert "github.com/go-yaml/yaml" in names

    def test_pom_xml(self, tmp_path: object) -> None:
        """Parse <dependency> blocks from a Maven pom.xml."""
        import pathlib

        root = pathlib.Path(tmp_path)  # type: ignore[arg-type]
        pom = root / "pom.xml"
        pom.write_text(
            textwrap.dedent("""\
                <project>
                  <dependencies>
                    <dependency>
                      <groupId>org.slf4j</groupId>
                      <artifactId>slf4j-api</artifactId>
                      <version>2.0.9</version>
                    </dependency>
                  </dependencies>
                </project>
            """),
            encoding="utf-8",
        )

        deps = ingest_manifest_dependencies(str(root))
        assert len(deps) == 1
        assert deps[0]["name"] == "slf4j-api"
        assert deps[0]["version"] == "2.0.9"

    def test_skips_node_modules_manifests(self, tmp_path: object) -> None:
        """Manifests inside node_modules/ should be excluded."""
        import pathlib

        root = pathlib.Path(tmp_path)  # type: ignore[arg-type]
        nm_pkg = root / "node_modules" / "pkg"
        nm_pkg.mkdir(parents=True)
        (nm_pkg / "package.json").write_text(
            json.dumps({"dependencies": {"foo": "^1.0.0"}}),
            encoding="utf-8",
        )
        # Put a real manifest at root level
        (root / "requirements.txt").write_text("requests==2.31.0\n", encoding="utf-8")

        deps = ingest_manifest_dependencies(str(root))
        names = {d["name"] for d in deps}
        assert "requests" in names
        assert "foo" not in names

    def test_raises_on_nonexistent_path(self) -> None:
        with pytest.raises(FileNotFoundError):
            ingest_manifest_dependencies("/no/such/dir/ecdat_test_404")

    def test_empty_directory(self, tmp_path: object) -> None:
        """An empty directory should yield zero deps."""
        import pathlib

        root = pathlib.Path(tmp_path)  # type: ignore[arg-type]
        assert ingest_manifest_dependencies(str(root)) == []


# ---------------------------------------------------------------------------
# ingest_git_url — network-gated
# ---------------------------------------------------------------------------


class TestIngestGitUrl:
    """Clone tests require network access and are skipped by default."""

    @pytest.mark.network
    def test_clone_success(self, tmp_path: object) -> None:
        """Clone a small public repo and verify the directory exists."""
        import pathlib

        workdir = str(pathlib.Path(tmp_path) / "cloned")  # type: ignore[arg-type]
        result_path = ingest_git_url(
            "https://github.com/octocat/Hello-World.git",
            workdir=workdir,
        )
        import os

        assert os.path.isdir(result_path)
        # The repo should contain at least a README.
        assert any(
            name.startswith("README")
            for name in os.listdir(result_path)
        )

    @pytest.mark.network
    def test_clone_bad_url_raises(self, tmp_path: object) -> None:
        """Cloning a non-existent URL should raise RuntimeError."""
        import pathlib

        workdir = str(pathlib.Path(tmp_path) / "fail")  # type: ignore[arg-type]
        with pytest.raises(RuntimeError, match="Could not clone repository"):
            ingest_git_url(
                "https://github.com/does-not-exist-ecdat-test-99999.git",
                workdir=workdir,
            )


# ---------------------------------------------------------------------------
# validate_git_url — SSRF protection (no network needed: IP literals and
# rejections-before-DNS only)
# ---------------------------------------------------------------------------


class TestValidateGitUrl:
    """Reject non-https schemes and non-public resolved addresses."""

    @pytest.mark.parametrize(
        "bad_url",
        [
            "file:///etc/passwd",
            "git://github.com/org/repo.git",
            "ssh://git@github.com/org/repo.git",
            "http://example.com/org/repo.git",
            "github.com/profm0r14rty/ECDAT",  # no scheme at all
            "not-a-url",
        ],
    )
    def test_rejects_non_https_schemes(self, bad_url: str) -> None:
        """file/git/ssh/http and scheme-less strings are rejected."""
        with pytest.raises(ValueError, match="Only https://"):
            validate_git_url(bad_url)

    @pytest.mark.parametrize(
        "internal_url",
        [
            "https://127.0.0.1/repo.git",  # loopback
            "https://169.254.169.254/latest/meta-data/",  # cloud metadata / link-local
            "https://10.0.0.5/repo.git",  # RFC1918 private
            "https://192.168.1.10/org/repo.git",  # RFC1918 private
        ],
    )
    def test_rejects_internal_addresses(self, internal_url: str) -> None:
        """Any resolved address that is private/loopback/link-local is rejected."""
        with pytest.raises(ValueError, match="non-public address"):
            validate_git_url(internal_url)

    def test_accepts_public_ip_literal(self) -> None:
        """A public literal IP passes validation (no DNS needed)."""
        validate_git_url("https://1.1.1.1/org/repo.git")

    def test_allowlist_rejects_unlisted_host(self, monkeypatch) -> None:
        """GIT_URL_ALLOWED_HOSTS restricts hosts even before the IP check."""
        monkeypatch.setenv("GIT_URL_ALLOWED_HOSTS", "github.com,gitlab.com")
        with pytest.raises(ValueError, match="GIT_URL_ALLOWED_HOSTS allowlist"):
            validate_git_url("https://127.0.0.1/repo.git")

    def test_allowlist_does_not_bypass_ip_checks(self, monkeypatch) -> None:
        """A listed host still fails if it resolves to a non-public address."""
        monkeypatch.setenv("GIT_URL_ALLOWED_HOSTS", "127.0.0.1")
        with pytest.raises(ValueError, match="non-public address"):
            validate_git_url("https://127.0.0.1/repo.git")

    def test_allowlisted_public_literal_passes(self, monkeypatch) -> None:
        """Both conditions met: on the allowlist AND a public address."""
        monkeypatch.setenv("GIT_URL_ALLOWED_HOSTS", "1.1.1.1")
        validate_git_url("https://1.1.1.1/org/repo.git")

    def test_rejects_url_without_hostname(self) -> None:
        """A URL with no hostname at all is rejected."""
        with pytest.raises(ValueError, match="no hostname"):
            validate_git_url("https:///path/to/repo")


# ---------------------------------------------------------------------------
# ingest_git_url — post-clone size ceiling (subprocess.run faked, no network)
# ---------------------------------------------------------------------------


class _FakeCloneResult:
    """Minimal stand-in for a successful ``subprocess.run`` result."""

    returncode = 0
    stderr = ""


def _fake_successful_clone(payload: bytes):
    """Return a ``subprocess.run`` fake that writes *payload* into the target dir."""

    def _run(cmd, capture_output=True, text=True, timeout=None):
        import pathlib

        target = pathlib.Path(cmd[-1])
        target.mkdir(parents=True, exist_ok=True)
        (target / "payload.bin").write_bytes(payload)
        return _FakeCloneResult()

    return _run


class TestGitUrlSizeCeiling:
    """``GIT_URL_MAX_SIZE_MB`` aborts oversized clones cleanly."""

    def test_over_limit_aborts_and_removes_temp_dir(
        self, monkeypatch, tmp_path: object
    ) -> None:
        """Exceeding the ceiling raises and cleans up the temp clone."""
        import pathlib

        import ecdat_core.ingestion as ingestion

        clone_dir = pathlib.Path(tmp_path) / "clone"  # type: ignore[arg-type]
        monkeypatch.setenv("GIT_URL_MAX_SIZE_MB", "1")
        monkeypatch.setattr(ingestion.tempfile, "mkdtemp", lambda prefix="": str(clone_dir))
        monkeypatch.setattr(
            ingestion.subprocess, "run", _fake_successful_clone(b"x" * (2 * 1024 * 1024))
        )

        with pytest.raises(RuntimeError, match="GIT_URL_MAX_SIZE_MB"):
            ingest_git_url("https://1.1.1.1/org/huge.git")
        assert not clone_dir.exists()

    def test_over_limit_keeps_provided_workdir(
        self, monkeypatch, tmp_path: object
    ) -> None:
        """A caller-provided workdir is left in place when the ceiling trips."""
        import pathlib

        import ecdat_core.ingestion as ingestion

        workdir = pathlib.Path(tmp_path) / "work"  # type: ignore[arg-type]
        monkeypatch.setenv("GIT_URL_MAX_SIZE_MB", "1")
        monkeypatch.setattr(
            ingestion.subprocess, "run", _fake_successful_clone(b"x" * (2 * 1024 * 1024))
        )

        with pytest.raises(RuntimeError, match="GIT_URL_MAX_SIZE_MB"):
            ingest_git_url("https://1.1.1.1/org/huge.git", workdir=str(workdir))
        assert workdir.exists()

    def test_within_limit_returns_clone_path(
        self, monkeypatch, tmp_path: object
    ) -> None:
        """A repo under the ceiling clones successfully (well-formed URL path)."""
        import pathlib

        import ecdat_core.ingestion as ingestion

        workdir = pathlib.Path(tmp_path) / "ok"  # type: ignore[arg-type]
        monkeypatch.setenv("GIT_URL_MAX_SIZE_MB", "100")
        monkeypatch.setattr(
            ingestion.subprocess, "run", _fake_successful_clone(b"tiny repo")
        )

        result = ingest_git_url("https://1.1.1.1/org/repo.git", workdir=str(workdir))
        assert result == str(workdir)
        assert (workdir / "payload.bin").read_bytes() == b"tiny repo"


# ---------------------------------------------------------------------------
# validate_local_path / ingest_local_directory — workspace sandbox
# ---------------------------------------------------------------------------


class TestLocalPathWorkspaceSandbox:
    """``SCAN_WORKSPACE_ROOT`` blocks arbitrary path reads."""

    def test_rejects_path_outside_configured_workspace(
        self, monkeypatch, tmp_path: object
    ) -> None:
        """A path outside the configured workspace root is rejected."""
        import pathlib

        ws = pathlib.Path(tmp_path) / "ws"  # type: ignore[arg-type]
        ws.mkdir()
        outside = pathlib.Path(tmp_path) / "outside"  # type: ignore[arg-type]
        outside.mkdir()
        monkeypatch.setenv("SCAN_WORKSPACE_ROOT", str(ws))

        with pytest.raises(ValueError, match="outside SCAN_WORKSPACE_ROOT"):
            validate_local_path(str(outside))
        with pytest.raises(ValueError, match="outside SCAN_WORKSPACE_ROOT"):
            list(ingest_local_directory(str(outside)))

    def test_rejects_symlink_escape(self, monkeypatch, tmp_path: object) -> None:
        """A symlink inside the workspace pointing outside is rejected."""
        import pathlib

        ws = pathlib.Path(tmp_path) / "ws"  # type: ignore[arg-type]
        ws.mkdir()
        secret = pathlib.Path(tmp_path) / "secret"  # type: ignore[arg-type]
        secret.mkdir()
        (secret / "key.py").write_text("x = 1\n", encoding="utf-8")
        link = ws / "escape"
        link.symlink_to(secret, target_is_directory=True)
        monkeypatch.setenv("SCAN_WORKSPACE_ROOT", str(ws))

        with pytest.raises(ValueError, match="outside SCAN_WORKSPACE_ROOT"):
            validate_local_path(str(link))

    def test_accepts_path_inside_workspace(self, monkeypatch, tmp_path: object) -> None:
        """Nested paths inside the workspace still scan normally."""
        import pathlib

        ws = pathlib.Path(tmp_path) / "ws"  # type: ignore[arg-type]
        repo = ws / "repo"
        repo.mkdir(parents=True)
        (repo / "app.py").write_text("x = 1\n", encoding="utf-8")
        monkeypatch.setenv("SCAN_WORKSPACE_ROOT", str(ws))

        assert validate_local_path(str(repo)) == str(repo.resolve())
        results = list(ingest_local_directory(str(repo)))
        assert [r[0].endswith("app.py") for r in results] == [True]

    def test_accepts_workspace_root_itself(self, monkeypatch, tmp_path: object) -> None:
        """The workspace root itself is a valid scan path."""
        import pathlib

        ws = pathlib.Path(tmp_path) / "ws"  # type: ignore[arg-type]
        ws.mkdir()
        monkeypatch.setenv("SCAN_WORKSPACE_ROOT", str(ws))
        assert validate_local_path(str(ws)) == str(ws.resolve())

    def test_default_workspace_is_fixtures_root(self, monkeypatch) -> None:
        """With SCAN_WORKSPACE_ROOT unset the bundled fixtures stay scannable."""
        import pathlib

        monkeypatch.delenv("SCAN_WORKSPACE_ROOT", raising=False)
        fixtures = pathlib.Path(__file__).parent / "fixtures"

        # The existing demo fixture scans keep working unchanged...
        assert validate_local_path(str(fixtures / "demo_repo")) == str(
            (fixtures / "demo_repo").resolve()
        )
        assert len(list(ingest_local_directory(str(fixtures / "demo_repo")))) > 0
        # ...while arbitrary paths stay blocked.
        with pytest.raises(ValueError, match="outside SCAN_WORKSPACE_ROOT"):
            validate_local_path("/tmp")

    def test_manifest_deps_respects_sandbox(self, monkeypatch, tmp_path: object) -> None:
        """ingest_manifest_dependencies enforces the same containment rule."""
        import pathlib

        ws = pathlib.Path(tmp_path) / "ws"  # type: ignore[arg-type]
        ws.mkdir()
        outside = pathlib.Path(tmp_path) / "outside"  # type: ignore[arg-type]
        outside.mkdir()
        (outside / "requirements.txt").write_text("requests==2.31.0\n", encoding="utf-8")
        monkeypatch.setenv("SCAN_WORKSPACE_ROOT", str(ws))

        with pytest.raises(ValueError, match="outside SCAN_WORKSPACE_ROOT"):
            ingest_manifest_dependencies(str(outside))
