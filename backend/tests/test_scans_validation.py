"""Phase 47 request-validation tests: schema-level bounds on scan creation and
risk-override bodies produce clean 422s with useful messages (never stack
traces), before any ingestion or background work happens.

The 422 error messages come from FastAPI's standard request-validation handler
(body parsed as JSON, ``detail`` = a list of ``{loc, msg, type}`` entries).
Negative override values are covered by ``test_scans_phase13.py``
(``test_patch_negative_override_rejected``); this module covers the new
bounds: target length, git_url URL shape, and absurd year magnitudes.
"""

from __future__ import annotations

import pytest

from conftest import DEMO_REPO, wait_for_scan_done


def _detail_messages(response) -> list[str]:
    """The human-readable messages from a 422 body's detail list."""
    detail = response.json()["detail"]
    assert isinstance(detail, list) and detail, "expected Pydantic error list"
    return [err["msg"] for err in detail]


# ---------------------------------------------------------------------------
# POST /api/scans body validation
# ---------------------------------------------------------------------------


def test_oversized_target_is_422(client) -> None:
    """A target longer than 2048 chars is rejected with a useful 422."""
    response = client.post(
        "/api/scans",
        json={"source_type": "local_path", "target": "x" * 2049},
    )
    assert response.status_code == 422
    assert any("2048" in msg for msg in _detail_messages(response))


@pytest.mark.parametrize("bad_target", ["not-a-url", "foo/bar", "https://"])
def test_git_url_garbage_rejected_at_schema_layer(client, bad_target: str) -> None:
    """Scheme-less strings and a scheme with no host are obvious garbage for a
    git_url: rejected 422 at the Pydantic layer before reaching ingestion."""
    response = client.post(
        "/api/scans",
        json={"source_type": "git_url", "target": bad_target},
    )
    assert response.status_code == 422
    assert any("URL" in msg for msg in _detail_messages(response))


def test_git_url_url_shaped_but_wrong_scheme_still_hits_ingestion(client) -> None:
    """Shape-valid non-https URLs pass the schema layer and keep getting the
    clear 400 from ingestion (https-only policy lives in one place)."""
    response = client.post(
        "/api/scans",
        json={"source_type": "git_url", "target": "http://example.com/org/repo.git"},
    )
    assert response.status_code == 400
    assert "Only https://" in response.json()["detail"]


def test_local_path_target_bounds_unchanged_for_fixture(client) -> None:
    """The legitimate demo_repo local-path scan still passes schema checks."""
    response = client.post(
        "/api/scans",
        json={"source_type": "local_path", "target": str(DEMO_REPO)},
    )
    assert response.status_code == 202


# ---------------------------------------------------------------------------
# PATCH /api/scans/{id}/artefacts/{detection_id} body validation
# ---------------------------------------------------------------------------


def _rsa_detection_id(client) -> tuple[str, str]:
    """Run a demo_repo scan to completion and return (scan_id, rsa_id)."""
    created = client.post(
        "/api/scans",
        json={"source_type": "local_path", "target": str(DEMO_REPO)},
    )
    assert created.status_code == 202
    scan_id = created.json()["id"]
    wait_for_scan_done(client, scan_id)
    items = client.get(
        f"/api/scans/{scan_id}/artefacts", params={"algorithm_family": "RSA"}
    ).json()["items"]
    assert len(items) == 1
    return scan_id, items[0]["id"]


def test_patch_absurd_year_magnitudes_rejected(client) -> None:
    """Shelf/migration horizons of 10000 / 500 years are absurd: 422 with a
    clear upper-bound message."""
    scan_id, detection_id = _rsa_detection_id(client)
    patch_url = f"/api/scans/{scan_id}/artefacts/{detection_id}"

    response = client.patch(patch_url, json={"shelf_life_years": 10000})
    assert response.status_code == 422
    assert any(
        "less than or equal to 200" in msg for msg in _detail_messages(response)
    )

    response = client.patch(patch_url, json={"migration_time_years": 500})
    assert response.status_code == 422
    assert any(
        "less than or equal to 200" in msg for msg in _detail_messages(response)
    )


def test_patch_boundary_values_accepted(client) -> None:
    """0 and 200 (the inclusive bounds) still re-run the risk engine."""
    scan_id, detection_id = _rsa_detection_id(client)
    response = client.patch(
        f"/api/scans/{scan_id}/artefacts/{detection_id}",
        json={"shelf_life_years": 0, "migration_time_years": 200},
    )
    assert response.status_code == 200
    assert response.json()["risk_assessment"]["shelf_life_years"] == 0
    assert response.json()["risk_assessment"]["migration_time_years"] == 200