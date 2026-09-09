"""Phase 15 end-to-end integration test: the full Batch 2 API surface.

One test drives the entire Batch 2 API in a single flow against a throwaway
SQLite database (Redis faked via fakeredis per Phase 11's convention, through
the shared conftest ``db_session_factory`` / ``client`` fixtures):

1. ``POST /api/scans`` — create a ``local_path`` scan of the demo_repo
   fixture, expect ``202`` and capture the scan id.
2. ``GET /api/scans/{scan_id}`` — poll until ``status=="done"`` (timeout-
   guarded by :func:`conftest.wait_for_scan_done`).
3. ``GET /api/scans/{scan_id}/artefacts`` — the fixture's Fix-Batch corrected
   counts (13 total; 6 critical after Fix Phase 5 dedup), with the critical
   filter spanning both ``classically_broken=True`` (MD5/DES — broken today,
   independent of quantum) and ``classically_broken=False`` (RSA-1024 — Mosca
   critical).
4. ``GET /api/scans/{scan_id}/cbom`` — a well-formed CycloneDX 1.6 BOM whose
   component count matches the artefact count.
5. ``PATCH /api/scans/{scan_id}/artefacts/{detection_id}`` — override one
   artefact's ``shelf_life_years`` and assert the recomputed ``urgency_ratio``
   follows Mosca's formula, then re-GET the artefact to confirm the override
   persisted.

The demo_repo fixture resolves to 4 files / 13 detections (after Fix Phase 5's
same-line dedup): RSA-1024 (critical, Mosca), MD5 x4 + DES (critical,
classically broken), and 7 quantum-safe.
"""

from __future__ import annotations

import pytest

from conftest import DEMO_REPO, wait_for_scan_done

# Fix-Batch corrected fixture numbers for a demo_repo scan (see progress.md:
# Phase 12 row and "CLI Summary (corrected output)"); Fix Phase 5 dedup lowered
# the totals from 17/7 to 13/6.
_TOTAL_DETECTIONS = 13
_TOTAL_CRITICAL = 6


def test_full_batch2_api_surface_end_to_end(client):
    """POST scan -> poll done -> artefacts -> cbom -> PATCH override, in one flow."""
    # --- 1. Create the scan -------------------------------------------------
    response = client.post(
        "/api/scans",
        json={"source_type": "local_path", "target": str(DEMO_REPO)},
    )
    assert response.status_code == 202
    created = response.json()
    assert created["status"] == "queued"
    scan_id = created["id"]
    assert scan_id

    # --- 2. Poll until done (timeout-guarded) -------------------------------
    detail = wait_for_scan_done(client, scan_id)
    assert detail["status"] == "done"
    assert detail["files_scanned"] == 4
    assert detail["error_message"] is None

    # --- 3. Artefacts: count + critical filter _______________________________
    all_artefacts = client.get(f"/api/scans/{scan_id}/artefacts")
    assert all_artefacts.status_code == 200
    body = all_artefacts.json()
    assert body["total"] == _TOTAL_DETECTIONS
    assert body["total_pages"] == 1
    assert len(body["items"]) == _TOTAL_DETECTIONS

    critical = client.get(
        f"/api/scans/{scan_id}/artefacts", params={"risk_level": "critical"}
    )
    assert critical.status_code == 200
    crit_body = critical.json()
    assert crit_body["total"] == _TOTAL_CRITICAL
    assert len(crit_body["items"]) == _TOTAL_CRITICAL
    assert all(
        item["risk_assessment"]["risk_level"] == "critical"
        for item in crit_body["items"]
    )

    # The Fix Batch split: classically-broken (MD5/DES) and Mosca-critical
    # (RSA-1024) artefacts must both appear among the critical detections.
    classically_broken = [
        item for item in crit_body["items"] if item["classically_broken"]
    ]
    mosca_only = [
        item for item in crit_body["items"] if not item["classically_broken"]
    ]
    assert classically_broken, "expected >=1 classically_broken critical artefact"
    assert mosca_only, "expected >=1 Mosca-only critical artefact"
    assert all(item["algorithm_family"] in {"MD5", "DES"} for item in classically_broken)
    assert all(item["algorithm_family"] == "RSA" for item in mosca_only)

    # --- 4. CBOM export ------------------------------------------------------
    cbom_response = client.get(f"/api/scans/{scan_id}/cbom")
    assert cbom_response.status_code == 200
    assert cbom_response.headers["content-disposition"] == (
        "attachment; filename=cbom.json"
    )
    bom = cbom_response.json()  # parses as JSON by construction
    assert bom["bomFormat"] == "CycloneDX"
    assert bom["specVersion"] == "1.6"
    assert len(bom["components"]) == _TOTAL_DETECTIONS
    assert all(
        component["type"] == "cryptographic-asset"
        for component in bom["components"]
    )

    # --- 5. Per-artefact risk override + persistence -------------------------
    rsa = client.get(
        f"/api/scans/{scan_id}/artefacts", params={"algorithm_family": "RSA"}
    ).json()["items"]
    assert len(rsa) == 1
    detection_id = rsa[0]["id"]

    # Baseline: RSA-1024 in auth/login.py → Mosca critical at (0.5 + 10) / 4.5.
    baseline = rsa[0]["risk_assessment"]
    assert baseline["risk_level"] == "critical"
    assert baseline["urgency_ratio"] == pytest.approx(10.5 / 4.5)

    # Shrink the shelf life to zero: urgency collapses to (X + 0) / Z -> low.
    patched = client.patch(
        f"/api/scans/{scan_id}/artefacts/{detection_id}",
        json={"shelf_life_years": 0},
    )
    assert patched.status_code == 200
    updated = patched.json()
    assert updated["id"] == detection_id
    updated_risk = updated["risk_assessment"]
    assert updated_risk["shelf_life_years"] == 0
    expected_urgency = (
        updated_risk["migration_time_years"] + 0.0
    ) / updated_risk["threat_horizon_years"]
    assert updated_risk["urgency_ratio"] == pytest.approx(expected_urgency)
    assert updated_risk["urgency_ratio"] == pytest.approx(0.5 / 4.5)
    assert updated_risk["risk_level"] == "low"
    assert updated_risk["urgency_ratio"] < baseline["urgency_ratio"]
    assert updated_risk["mosca_violation"] is False

    # Re-GET confirms the override persisted.
    again = client.get(
        f"/api/scans/{scan_id}/artefacts", params={"algorithm_family": "RSA"}
    ).json()["items"]
    assert len(again) == 1
    persisted = again[0]["risk_assessment"]
    assert again[0]["id"] == detection_id
    assert persisted["shelf_life_years"] == 0
    assert persisted["urgency_ratio"] == pytest.approx(0.5 / 4.5)
    assert persisted["risk_level"] == "low"