"""Phase 13 API tests: artefact listing, CBOM/report export, risk overrides.

Covers:

- Filtered + paginated ``GET /api/scans/{id}/artefacts`` (correct counts,
  page metadata, per-item flattening).
- ``GET /api/scans/{id}/cbom`` downloads a structurally valid CycloneDX 1.6
  BOM with the ``Content-Disposition`` attachment header.
- ``GET /api/scans/{id}/report`` exactly matches the scan detail summary.
- ``PATCH /api/scans/{id}/artefacts/{detection_id}`` re-runs the risk engine
  with overrides, persists the result, and a subsequent GET reflects it.
- 404 for unknown scans / foreign detections, 409 while a scan is queued or
  running.

All scans run for real against the demo_repo fixture (17 detections:
RSA-1024 critical, MD5 x5 + DES critical via classical break, 10
quantum-safe) through the shared conftest ``client`` / ``db_session_factory``
fixtures.
"""

from __future__ import annotations

import pytest

from conftest import DEMO_REPO, wait_for_scan_done

_ALLOWED_ASSET_TYPES = {
    "algorithm",
    "certificate",
    "protocol",
    "related-crypto-material",
}


def _scan_demo_repo(client) -> str:
    """POST a demo_repo scan and wait for it to finish; return its id."""
    response = client.post(
        "/api/scans",
        json={"source_type": "local_path", "target": str(DEMO_REPO)},
    )
    assert response.status_code == 202
    scan_id = response.json()["id"]
    wait_for_scan_done(client, scan_id)
    return scan_id


def _created_scan_via_repository(db_session_factory) -> str:
    """Create a queued ScanRun directly (no background job scheduled)."""
    from backend.app.repository import create_scan_run

    session = db_session_factory()
    try:
        return create_scan_run(
            session, target="/definitely-not-scanned", source_type="local_path"
        ).id
    finally:
        session.close()


# ---------------------------------------------------------------------------
# GET /api/scans/{scan_id}/artefacts
# ---------------------------------------------------------------------------


def test_artefacts_list_pagination_counts(client):
    """Pagination slices match: 17 total, 4 pages of 5, last page has 2."""
    scan_id = _scan_demo_repo(client)

    page1 = client.get(
        f"/api/scans/{scan_id}/artefacts", params={"page": 1, "page_size": 5}
    )
    assert page1.status_code == 200
    body = page1.json()
    assert body["total"] == 17
    assert body["page"] == 1
    assert body["page_size"] == 5
    assert body["total_pages"] == 4
    assert len(body["items"]) == 5

    page4 = client.get(
        f"/api/scans/{scan_id}/artefacts", params={"page": 4, "page_size": 5}
    )
    assert page4.status_code == 200
    assert len(page4.json()["items"]) == 2

    # Defaults: page=1, page_size=50 -> everything on one page.
    all_items = client.get(f"/api/scans/{scan_id}/artefacts")
    assert all_items.status_code == 200
    assert all_items.json()["total_pages"] == 1
    assert len(all_items.json()["items"]) == 17


def test_artefacts_list_filters_and_flattened_shape(client):
    """risk_level / algorithm_family filters return correct counts and items."""
    scan_id = _scan_demo_repo(client)

    critical = client.get(
        f"/api/scans/{scan_id}/artefacts", params={"risk_level": "critical"}
    )
    assert critical.status_code == 200
    crit_body = critical.json()
    assert crit_body["total"] == 7
    assert crit_body["total_pages"] == 1
    assert all(
        item["risk_assessment"]["risk_level"] == "critical"
        for item in crit_body["items"]
    )

    quantum_safe = client.get(
        f"/api/scans/{scan_id}/artefacts", params={"risk_level": "quantum-safe"}
    )
    assert quantum_safe.status_code == 200
    assert quantum_safe.json()["total"] == 10
    assert all(
        item["risk_assessment"]["risk_level"] == "quantum-safe"
        for item in quantum_safe.json()["items"]
    )

    md5 = client.get(
        f"/api/scans/{scan_id}/artefacts", params={"algorithm_family": "MD5"}
    )
    assert md5.status_code == 200
    md5_body = md5.json()
    assert md5_body["total"] == 5
    assert all(item["algorithm_family"] == "MD5" for item in md5_body["items"])

    # Combined filter: all MD5 detections are classically-broken critical.
    combined = client.get(
        f"/api/scans/{scan_id}/artefacts",
        params={"risk_level": "critical", "algorithm_family": "MD5"},
    )
    assert combined.status_code == 200
    assert combined.json()["total"] == 5

    # Per-item shape: detection fields flattened with nested risk/recommendation.
    first = md5_body["items"][0]
    assert set(first) == {
        "id",
        "file_path",
        "line_number",
        "matched_text",
        "asset_type",
        "algorithm_family",
        "key_size_bits",
        "quantum_vulnerable",
        "classically_broken",
        "confidence",
        "language",
        "detection_method",
        "risk_assessment",
        "recommendation",
    }
    assert first["classically_broken"] is True
    assert first["quantum_vulnerable"] is False
    assert set(first["risk_assessment"]) == {
        "migration_time_years",
        "shelf_life_years",
        "threat_horizon_years",
        "urgency_ratio",
        "risk_level",
        "mosca_violation",
    }
    assert set(first["recommendation"]) == {
        "recommended_algorithm",
        "fips_reference",
        "rationale",
        "latency_note",
        "migration_note",
    }


def test_artefacts_list_query_validation(client):
    """Invalid page/page_size request params must be 422s."""
    scan_id = _scan_demo_repo(client)

    assert (
        client.get(
            f"/api/scans/{scan_id}/artefacts", params={"page": 0}
        ).status_code
        == 422
    )
    assert (
        client.get(
            f"/api/scans/{scan_id}/artefacts", params={"page_size": 501}
        ).status_code
        == 422
    )


# ---------------------------------------------------------------------------
# GET /api/scans/{scan_id}/cbom
# ---------------------------------------------------------------------------


def test_cbom_download_valid_cyclonedx(client):
    """CBOM download: attachment header + structurally valid CycloneDX 1.6."""
    scan_id = _scan_demo_repo(client)

    response = client.get(f"/api/scans/{scan_id}/cbom")
    assert response.status_code == 200
    assert response.headers["content-disposition"] == (
        "attachment; filename=cbom.json"
    )
    assert response.headers["content-type"].startswith("application/json")

    bom = response.json()
    assert bom["bomFormat"] == "CycloneDX"
    assert bom["specVersion"] == "1.6"
    assert bom["serialNumber"].startswith("urn:uuid:")
    assert bom["metadata"]["component"]["name"] == str(DEMO_REPO)

    components = bom["components"]
    assert len(components) == 17
    for component in components:
        assert component["type"] == "cryptographic-asset"
        assert component["bom-ref"]
        assert component["name"]
        assert component["cryptoProperties"]["assetType"] in _ALLOWED_ASSET_TYPES
        ecdat_props = {
            prop["name"]: prop["value"] for prop in component["properties"]
        }
        assert ecdat_props["ecdat:riskLevel"] in {
            "critical",
            "high",
            "medium",
            "low",
            "quantum-safe",
        }
        assert ecdat_props["ecdat:quantumVulnerable"] in {"True", "False"}
        assert ecdat_props["ecdat:classicallyBroken"] in {"True", "False"}

    # A second download is still a valid BOM (serialNumber may legitimately
    # differ per export, so only assert the structural contract).
    again = client.get(f"/api/scans/{scan_id}/cbom")
    assert again.status_code == 200
    assert again.json()["bomFormat"] == "CycloneDX"
    assert again.json()["specVersion"] == "1.6"
    assert len(again.json()["components"]) == 17


# ---------------------------------------------------------------------------
# GET /api/scans/{scan_id}/report
# ---------------------------------------------------------------------------


def test_report_matches_scan_detail_summary(client):
    """The report endpoint payload equals the detail endpoint's summary."""
    scan_id = _scan_demo_repo(client)

    detail = client.get(f"/api/scans/{scan_id}")
    assert detail.status_code == 200
    summary_from_detail = detail.json()["summary"]

    report = client.get(f"/api/scans/{scan_id}/report")
    assert report.status_code == 200
    assert report.json() == summary_from_detail
    assert report.json()["total_detections"] == 17
    assert report.json()["risk_level_counts"]["critical"] == 7


# ---------------------------------------------------------------------------
# PATCH /api/scans/{scan_id}/artefacts/{detection_id}
# ---------------------------------------------------------------------------


def _rsa_artefact(client, scan_id) -> dict:
    """Return the single RSA artefact from a finished demo_repo scan."""
    response = client.get(
        f"/api/scans/{scan_id}/artefacts", params={"algorithm_family": "RSA"}
    )
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    return items[0]


def test_patch_override_persists_and_get_reflects(client):
    """PATCH overrides change persisted risk_level/urgency; GET sees it."""
    scan_id = _scan_demo_repo(client)
    rsa = _rsa_artefact(client, scan_id)
    detection_id = rsa["id"]

    # Baseline from the scan: RSA-1024 in auth/login.py, Mosca critical.
    assert rsa["risk_assessment"]["risk_level"] == "critical"
    assert rsa["risk_assessment"]["urgency_ratio"] == pytest.approx(10.5 / 4.5)
    assert rsa["risk_assessment"]["mosca_violation"] is True

    # Override shelf life to zero: urgency (0.5 + 0) / 4.5 -> low.
    patch = client.patch(
        f"/api/scans/{scan_id}/artefacts/{detection_id}",
        json={"shelf_life_years": 0, "migration_time_years": 0.5},
    )
    assert patch.status_code == 200
    updated = patch.json()
    assert updated["id"] == detection_id
    assert updated["risk_assessment"]["shelf_life_years"] == 0
    assert updated["risk_assessment"]["migration_time_years"] == 0.5
    assert updated["risk_assessment"]["urgency_ratio"] == pytest.approx(
        0.5 / 4.5
    )
    assert updated["risk_assessment"]["risk_level"] == "low"
    assert updated["risk_assessment"]["mosca_violation"] is False

    # A subsequent GET reflects the persisted change.
    after_get = client.get(
        f"/api/scans/{scan_id}/artefacts", params={"algorithm_family": "RSA"}
    )
    assert after_get.status_code == 200
    seen = after_get.json()["items"][0]
    assert seen["id"] == detection_id
    assert seen["risk_assessment"]["risk_level"] == "low"
    assert seen["risk_assessment"]["urgency_ratio"] == pytest.approx(0.5 / 4.5)

    # Sending nulls resets to the default heuristics -> critical again.
    reset = client.patch(
        f"/api/scans/{scan_id}/artefacts/{detection_id}",
        json={"shelf_life_years": None, "migration_time_years": None},
    )
    assert reset.status_code == 200
    assert reset.json()["risk_assessment"]["risk_level"] == "critical"
    assert reset.json()["risk_assessment"]["urgency_ratio"] == pytest.approx(
        10.5 / 4.5
    )
    assert reset.json()["risk_assessment"]["shelf_life_years"] == 10.0


def test_patch_negative_override_rejected(client):
    """Negative shelf-life / migration-time overrides must be 422s."""
    scan_id = _scan_demo_repo(client)
    detection_id = _rsa_artefact(client, scan_id)["id"]

    response = client.patch(
        f"/api/scans/{scan_id}/artefacts/{detection_id}",
        json={"shelf_life_years": -1},
    )
    assert response.status_code == 422

    response = client.patch(
        f"/api/scans/{scan_id}/artefacts/{detection_id}",
        json={"migration_time_years": -0.5},
    )
    assert response.status_code == 422


def test_patch_detection_not_in_scan_returns_404(client, db_session_factory):
    """PATCHing a detection that belongs to another scan must be a 404."""
    scan_id = _scan_demo_repo(client)

    # Build a second, unrelated done scan with its own detection row.
    from backend.app.models_orm import (
        DetectionRow,
        RecommendationRow,
        RiskAssessmentRow,
        RiskLevel,
        ScanRun,
        ScanStatus,
        SourceType,
    )
    from backend.app.repository import mark_scan_done

    session = db_session_factory()
    try:
        other = ScanRun(
            target="/other", source_type=SourceType.local_path,
            status=ScanStatus.queued,
        )
        session.add(other)
        session.commit()
        mark_scan_done(session, other.id, files_scanned=1)
        foreign_det = DetectionRow(
            scan_id=other.id,
            id="detection-in-other-scan",
            file_path="/other/secret.py",
            line_number=5,
            matched_text="RSA.generate(1024)",
            asset_type="algorithm",
            algorithm_family="RSA",
            key_size_bits=1024,
            quantum_vulnerable=True,
            classically_broken=False,
            confidence=0.95,
            language="Python",
            detection_method="regex",
        )
        session.add(foreign_det)
        session.add_all(
            [
                RiskAssessmentRow(
                    detection_id=foreign_det.id,
                    migration_time_years=0.5,
                    shelf_life_years=5.0,
                    threat_horizon_years=15.0,
                    urgency_ratio=0.4,
                    risk_level=RiskLevel.low,
                    mosca_violation=False,
                ),
                RecommendationRow(
                    detection_id=foreign_det.id,
                    recommended_algorithm="ML-KEM-512",
                    fips_reference="FIPS 203",
                    rationale="PQ replacement",
                    latency_note="~2x overhead",
                    migration_note="Moderate",
                ),
            ]
        )
        session.commit()
    finally:
        session.close()

    response = client.patch(
        f"/api/scans/{scan_id}/artefacts/detection-in-other-scan",
        json={"shelf_life_years": 1},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Detection not found in scan"

    # A completely unknown detection id is also a 404.
    response = client.patch(
        f"/api/scans/{scan_id}/artefacts/does-not-exist",
        json={"shelf_life_years": 1},
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Guards: 404 unknown scan, 409 while queued/running
# ---------------------------------------------------------------------------


def test_not_done_scan_returns_409(client, db_session_factory):
    """Queued/running scans get 409 on artefact, CBOM, report endpoints."""
    scan_id = _created_scan_via_repository(db_session_factory)

    artefact_url = f"/api/scans/{scan_id}/artefacts"
    cbom_url = f"/api/scans/{scan_id}/cbom"
    report_url = f"/api/scans/{scan_id}/report"
    patch_url = f"/api/scans/{scan_id}/artefacts/any-detection"

    for url in (artefact_url, cbom_url, report_url):
        response = client.get(url)
        assert response.status_code == 409
        assert response.json()["detail"] == "Scan not complete"

    patch = client.patch(patch_url, json={"shelf_life_years": 1})
    assert patch.status_code == 409
    assert patch.json()["detail"] == "Scan not complete"

    # Mark running directly and re-check the same guards.
    from backend.app.repository import mark_scan_running

    session = db_session_factory()
    try:
        mark_scan_running(session, scan_id)
    finally:
        session.close()

    for url in (artefact_url, cbom_url, report_url):
        assert client.get(url).status_code == 409

    # Once actually done, the same endpoints stop returning 409.
    done_id = _scan_demo_repo(client)
    assert client.get(f"/api/scans/{done_id}/artefacts").status_code == 200
    assert client.get(f"/api/scans/{done_id}/cbom").status_code == 200
    assert client.get(f"/api/scans/{done_id}/report").status_code == 200


def test_unknown_scan_returns_404(client):
    """Nonexistent scans get 404 (not 409) on artefact, CBOM, report."""
    for url in (
        "/api/scans/does-not-exist/artefacts",
        "/api/scans/does-not-exist/cbom",
        "/api/scans/does-not-exist/report",
    ):
        assert client.get(url).status_code == 404

    patch = client.patch(
        "/api/scans/does-not-exist/artefacts/any-detection",
        json={"shelf_life_years": 1},
    )
    assert patch.status_code == 404