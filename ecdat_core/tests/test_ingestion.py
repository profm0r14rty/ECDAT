"""Tests for ECDAT ingestion: directory walking, manifest extraction, Git clone.

Uses :mod:`pytest` ``tmp_path`` fixtures to build small directory trees on the
fly so no network or real repositories are required (except the clone tests
which are marked with ``@pytest.mark.network``).
"""

from __future__ import annotations

import json
import textwrap

import pytest

from ecdat_core.ingestion import (
    ingest_git_url,
    ingest_local_directory,
    ingest_manifest_dependencies,
)


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
        with pytest.raises(RuntimeError, match="git clone failed"):
            ingest_git_url(
                "https://github.com/does-not-exist-ecdat-test-99999.git",
                workdir=workdir,
            )
