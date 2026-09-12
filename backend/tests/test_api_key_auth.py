"""Phase 46 API-key gate tests: off-by-default no-op vs 401s when enabled.

The gate (:mod:`backend.app.security`) reads ``REQUIRE_API_KEY`` /
``API_KEYS`` from the environment **per request**, so ``monkeypatch`` toggles
it per test on the same app instance — and the rest of the suite (which never
touches these vars) exercises the off state unchanged, as it always has.
"""

from __future__ import annotations

import pytest

from conftest import DEMO_REPO

_VALID_KEYS = ["key-alpha", "key-beta", "key-gamma"]
# Whitespace around commas/keys is deliberate: parsing must trim (and drop
# empty entries) so `"a, , b"`-style configs work.
_API_KEYS_CSV = "key-alpha, key-beta ,key-gamma,"


def _auth_headers(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


def _enable_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REQUIRE_API_KEY", "true")
    monkeypatch.setenv("API_KEYS", _API_KEYS_CSV)


class TestGateOffByDefault:
    """Identical behavior to pre-Phase-46: no header, no key, no gate."""

    def test_post_scan_without_key_is_202(self, client) -> None:
        """The expensive endpoint works unauthenticated, exactly as today."""
        response = client.post(
            "/api/scans",
            json={"source_type": "local_path", "target": str(DEMO_REPO)},
        )
        assert response.status_code == 202

    def test_get_scans_without_key_is_200(self, client) -> None:
        """Read endpoints work unauthenticated, exactly as today."""
        response = client.get("/api/scans")
        assert response.status_code == 200

    def test_explicit_false_is_also_off(self, client, monkeypatch) -> None:
        """REQUIRE_API_KEY=false behaves like unset, even with API_KEYS set."""
        monkeypatch.setenv("REQUIRE_API_KEY", "false")
        monkeypatch.setenv("API_KEYS", "should-not-matter")
        response = client.post(
            "/api/scans",
            json={"source_type": "local_path", "target": str(DEMO_REPO)},
        )
        assert response.status_code == 202


class TestGateEnabled:
    """REQUIRE_API_KEY=true -> Bearer key required on every /api/scans route."""

    def test_post_without_key_is_401(self, client, monkeypatch) -> None:
        """Missing header is rejected with 401 + WWW-Authenticate: Bearer."""
        _enable_gate(monkeypatch)
        response = client.post(
            "/api/scans",
            json={"source_type": "local_path", "target": str(DEMO_REPO)},
        )
        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"

    def test_post_with_wrong_key_is_401(self, client, monkeypatch) -> None:
        """An unknown key is rejected with 401."""
        _enable_gate(monkeypatch)
        response = client.post(
            "/api/scans",
            json={"source_type": "local_path", "target": str(DEMO_REPO)},
            headers=_auth_headers("wrong-key"),
        )
        assert response.status_code == 401

    @pytest.mark.parametrize("key", _VALID_KEYS)
    def test_post_with_valid_key_is_202(
        self, client, monkeypatch, key: str
    ) -> None:
        """Any configured key (middle, second-after-trim, trailing-comma edge)
        is accepted — locking the comma/whitespace parsing."""
        _enable_gate(monkeypatch)
        response = client.post(
            "/api/scans",
            json={"source_type": "local_path", "target": str(DEMO_REPO)},
            headers=_auth_headers(key),
        )
        assert response.status_code == 202

    def test_non_bearer_scheme_is_401(self, client, monkeypatch) -> None:
        """A Basic header must not satisfy the Bearer requirement."""
        _enable_gate(monkeypatch)
        response = client.post(
            "/api/scans",
            json={"source_type": "local_path", "target": str(DEMO_REPO)},
            headers={"Authorization": "Basic dXNlcjpwYXNz"},
        )
        assert response.status_code == 401

    def test_read_endpoints_also_require_the_key(
        self, client, monkeypatch
    ) -> None:
        """(Documented decision) reads are gated too: list/detail/cbom all 401
        without a key — the leak being closed is read access to everyone's
        scan history, artefacts, and CBOM exports."""
        _enable_gate(monkeypatch)
        assert client.get("/api/scans").status_code == 401
        assert client.get("/api/scans/does-not-exist").status_code == 401
        assert client.get("/api/scans/does-not-exist/cbom").status_code == 401
        assert client.get("/api/scans/does-not-exist/report").status_code == 401
        listed = client.get("/api/scans", headers=_auth_headers(_VALID_KEYS[0]))
        assert listed.status_code == 200

    def test_401_wins_over_404_for_unknown_scan(self, client, monkeypatch) -> None:
        """Router-level dependency ordering: unauthenticated callers get 401,
        not 404, so they cannot probe scan existence."""
        _enable_gate(monkeypatch)
        response = client.get("/api/scans/does-not-exist")
        assert response.status_code == 401
        authenticated = client.get(
            "/api/scans/does-not-exist", headers=_auth_headers(_VALID_KEYS[0])
        )
        assert authenticated.status_code == 404

    def test_health_stays_open_when_gate_enabled(self, client, monkeypatch) -> None:
        """/health remains public: Render health checks, UptimeRobot
        warm-keeping, and the DEMO.md warm-up step all depend on it."""
        _enable_gate(monkeypatch)
        assert client.get("/health").status_code == 200

    @pytest.mark.parametrize("keys_env", [None, "", "   ", ","])
    def test_enabled_without_keys_is_fail_closed_500(
        self, client, monkeypatch, keys_env: str | None
    ) -> None:
        """Gate on + empty API_KEYS -> 500 with a clear message. A
        misconfigured 'protected' API must fail closed, never open up."""
        monkeypatch.setenv("REQUIRE_API_KEY", "true")
        if keys_env is None:
            monkeypatch.delenv("API_KEYS", raising=False)
        else:
            monkeypatch.setenv("API_KEYS", keys_env)
        response = client.post(
            "/api/scans",
            json={"source_type": "local_path", "target": str(DEMO_REPO)},
        )
        assert response.status_code == 500
        assert "API_KEYS" in response.json()["detail"]