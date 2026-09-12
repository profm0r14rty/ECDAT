"""API-level tests for Phase 45 ingestion security validation.

Verifies that ``POST /api/scans`` rejects, with a clear 400, targets that
fail ecdat_core's ingestion security checks — while the legitimate demo_repo
local-path scan keeps returning 202.  All targets are IP literals or rejected
before any DNS lookup, so no network access is required.

Uses the shared ``client`` fixture from conftest.py (throwaway SQLite +
fakeredis per Phase 11's convention).
"""

from __future__ import annotations

import pytest

from conftest import DEMO_REPO


class TestLocalPathSandbox:
    """``SCAN_WORKSPACE_ROOT`` violations are rejected with 400."""

    def test_local_path_outside_workspace_is_rejected(
        self, client, tmp_path, monkeypatch
    ) -> None:
        """An explicit workspace root that excludes demo_repo must 400 it."""
        monkeypatch.setenv("SCAN_WORKSPACE_ROOT", str(tmp_path))
        response = client.post(
            "/api/scans",
            json={"source_type": "local_path", "target": str(DEMO_REPO)},
        )
        assert response.status_code == 400
        assert "outside SCAN_WORKSPACE_ROOT" in response.json()["detail"]

    def test_etc_is_rejected(self, client) -> None:
        """Submitting /etc (arbitrary file read) must be a 400."""
        response = client.post(
            "/api/scans",
            json={"source_type": "local_path", "target": "/etc"},
        )
        assert response.status_code == 400
        assert "outside SCAN_WORKSPACE_ROOT" in response.json()["detail"]

    def test_demo_repo_still_accepted_by_default(self, client) -> None:
        """The existing fixture scan keeps working with zero config change."""
        response = client.post(
            "/api/scans",
            json={"source_type": "local_path", "target": str(DEMO_REPO)},
        )
        assert response.status_code == 202
        assert response.json()["status"] == "queued"


class TestGitUrlSsrFProtection:
    """Non-https / internal-target git URLs are rejected with 400."""

    @pytest.mark.parametrize(
        "bad_url",
        [
            "https://169.254.169.254/latest/meta-data/",
            "https://127.0.0.1/org/repo.git",
            "https://10.0.0.5/org/repo.git",
        ],
    )
    def test_internal_targets_are_rejected(self, client, bad_url: str) -> None:
        """Private/loopback/link-local hosts must 400 before any clone."""
        response = client.post(
            "/api/scans",
            json={"source_type": "git_url", "target": bad_url},
        )
        assert response.status_code == 400
        assert "non-public address" in response.json()["detail"]

    @pytest.mark.parametrize(
        "bad_url",
        [
            "git://github.com/org/repo.git",
            "ssh://git@github.com/org/repo.git",
            "http://example.com/org/repo.git",
        ],
    )
    def test_non_https_schemes_are_rejected(self, client, bad_url: str) -> None:
        """git/ssh/http URLs are URL-shaped (they pass the Phase 47 schema
        check) but fail ingestion's https-only policy with a clear 400."""
        response = client.post(
            "/api/scans",
            json={"source_type": "git_url", "target": bad_url},
        )
        assert response.status_code == 400
        assert "Only https://" in response.json()["detail"]

    @pytest.mark.parametrize(
        "garbage",
        [
            "file:///etc/passwd",
            "not-a-url",
        ],
    )
    def test_obvious_garbage_rejected_at_schema_layer(
        self, client, garbage: str
    ) -> None:
        """Phase 47: strings that are not URL-shaped at all (scheme-less, or a
        scheme with no host like ``file://``) are rejected 422 by the Pydantic
        layer before ingestion — previously they reached ``validate_git_url``
        and returned 400. Documented behavior change: same rejection intent,
        faster, with a schema-level message."""
        response = client.post(
            "/api/scans",
            json={"source_type": "git_url", "target": garbage},
        )
        assert response.status_code == 422