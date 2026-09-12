"""Phase 47 rate-limit tests: POST /api/scans is throttled per client.

Default spec is ``10/hour`` (env ``SCAN_CREATE_RATE_LIMIT``, read per
request); identity is key-based when the Phase 46 gate is on and a valid
Bearer key rides along, IP-based otherwise. The limiter's in-memory storage is
reset by conftest's autouse fixture so buckets never leak between tests.
Valid scan creations do run (they queue a real demo_repo background scan), so
every ``202`` also exercises the normal pipeline.
"""

from __future__ import annotations

import time

import pytest

from conftest import DEMO_REPO


def _post_scan(client, headers=None):
    """POST a demo_repo local_path scan with optional auth headers."""
    return client.post(
        "/api/scans",
        json={"source_type": "local_path", "target": str(DEMO_REPO)},
        headers=headers,
    )


class TestRateLimitIpBased:
    """Gate off (Phase 46 default): identity falls back to the remote IP."""

    def test_exceeding_limit_returns_clear_429(self, client, monkeypatch) -> None:
        """11th-equivalent request (here a 3rd under 2/minute) is a 429 with a
        clear detail message and a Retry-After header."""
        monkeypatch.setenv("SCAN_CREATE_RATE_LIMIT", "2/minute")
        assert _post_scan(client).status_code == 202
        assert _post_scan(client).status_code == 202

        blocked = _post_scan(client)
        assert blocked.status_code == 429
        body = blocked.json()
        assert "detail" in body
        assert "Rate limit exceeded" in body["detail"]
        assert "2 per 1 minute" in body["detail"]
        retry_after = blocked.headers.get("retry-after")
        assert retry_after is not None
        assert retry_after.isdigit()
        assert int(retry_after) >= 1

    def test_only_post_scans_is_rate_limited(self, client, monkeypatch) -> None:
        """Read endpoints and /health are untouched by the scan-create limit."""
        monkeypatch.setenv("SCAN_CREATE_RATE_LIMIT", "1/minute")
        assert _post_scan(client).status_code == 202
        assert client.get("/api/scans").status_code == 200
        assert client.get("/health").status_code == 200

    def test_validation_failures_do_not_consume_the_bucket(
        self, client, monkeypatch
    ) -> None:
        """A 422 (body rejected at the schema layer) never decrements the
        bucket; the first valid request still passes."""
        monkeypatch.setenv("SCAN_CREATE_RATE_LIMIT", "1/minute")
        garbage = client.post(
            "/api/scans",
            json={"source_type": "git_url", "target": "not-a-url"},
        )
        assert garbage.status_code == 422
        assert _post_scan(client).status_code == 202
        # Bucket now exhausted: the next valid request is throttled.
        assert _post_scan(client).status_code == 429

    def test_limit_resets_after_window_elapses(self, client, monkeypatch) -> None:
        """A ``2/second`` spec admits 2 requests, then 429, then a fresh
        window (after ~1s) admits again."""
        monkeypatch.setenv("SCAN_CREATE_RATE_LIMIT", "2/second")
        assert _post_scan(client).status_code == 202
        assert _post_scan(client).status_code == 202
        assert _post_scan(client).status_code == 429
        time.sleep(1.3)
        assert _post_scan(client).status_code == 202


class TestRateLimitKeyBasedWhenGateEnabled:
    """Gate on (Phase 46): valid API keys get per-key buckets."""

    def _enable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("REQUIRE_API_KEY", "true")
        monkeypatch.setenv("API_KEYS", "key-one,key-two")
        monkeypatch.setenv("SCAN_CREATE_RATE_LIMIT", "2/minute")

    def test_buckets_are_per_api_key(self, client, monkeypatch) -> None:
        """Exhausting key-one's bucket does not throttle key-two, and
        unauthenticated / unknown-key requests are rejected by the auth gate
        (401) without ever reaching the limiter."""
        self._enable(monkeypatch)
        key_one = {"Authorization": "Bearer key-one"}
        key_two = {"Authorization": "Bearer key-two"}

        assert _post_scan(client, key_one).status_code == 202
        assert _post_scan(client, key_one).status_code == 202
        assert _post_scan(client, key_one).status_code == 429

        assert _post_scan(client, key_two).status_code == 202
        assert _post_scan(client, {"Authorization": "Bearer unknown"}).status_code == 401
        assert _post_scan(client).status_code == 401

    def test_authenticated_429_still_shows_clear_body(
        self, client, monkeypatch
    ) -> None:
        """The 429 payload shape is identical whether the bucket is key- or
        IP-based."""
        self._enable(monkeypatch)
        key_one = {"Authorization": "Bearer key-one"}
        assert _post_scan(client, key_one).status_code == 202
        assert _post_scan(client, key_one).status_code == 202
        blocked = _post_scan(client, key_one)
        assert blocked.status_code == 429
        assert "Rate limit exceeded" in blocked.json()["detail"]
        assert blocked.headers.get("retry-after") is not None