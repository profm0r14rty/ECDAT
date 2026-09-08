"""End-to-end test for ECDAT: run_scan against the demo_repo fixture.

Validates the full pipeline (ingest -> detect -> assess -> recommend ->
assemble) over a realistic mixed-language fixture, and that the exported
CBOM is structurally valid CycloneDX 1.6 with an exhaustive component
set.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ecdat_core.cbom_export import export_cbom
from ecdat_core.cli import run_scan

_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "demo_repo"


@pytest.fixture(scope="module")
def scan_result():
    """Scan the demo_repo fixture once and reuse it across tests."""
    return run_scan(str(_FIXTURE_DIR))


def test_at_least_one_critical_detection(scan_result) -> None:
    """The legacy auth path (1024-bit RSA) must be assessed as critical."""
    levels = {ra.risk_level for ra in scan_result.risk_assessments}
    assert "critical" in levels


def test_at_least_one_quantum_safe_mlkem(scan_result) -> None:
    """The modern ML-KEM usage must be assessed as quantum-safe."""
    risk_by_detection = {
        ra.detection_id: ra.risk_level for ra in scan_result.risk_assessments
    }
    assert any(
        det.algorithm_family == "ML-KEM"
        and risk_by_detection.get(det.id) == "quantum-safe"
        for det in scan_result.detections
    )


def test_every_detection_has_assessment_and_recommendation(scan_result) -> None:
    """Each detection should have a matching risk assessment and recommendation."""
    assessed_ids = {ra.detection_id for ra in scan_result.risk_assessments}
    recommended_ids = {rec.detection_id for rec in scan_result.recommendations}
    detection_ids = {det.id for det in scan_result.detections}
    assert assessed_ids == detection_ids
    assert recommended_ids == detection_ids


def test_exported_cbom_structure(scan_result) -> None:
    """Exported CBOM is valid CycloneDX 1.6 with non-empty components."""
    cbom = export_cbom(scan_result)
    assert cbom["bomFormat"] == "CycloneDX"
    assert cbom["specVersion"] == "1.6"
    assert isinstance(cbom["components"], list)
    assert len(cbom["components"]) > 0
    assert all(
        component["type"] == "cryptographic-asset"
        for component in cbom["components"]
    )


def test_at_least_two_critical_detections_with_classically_broken_distinction(
    scan_result,
) -> None:
    """At least 2 distinct critical detections with differing classically_broken values.

    The Mosca-violation critical (RSA-1024) has classically_broken=False,
    while classically-broken artefacts (MD5, DES) have classically_broken=True.
    """
    critical_ras = [ra for ra in scan_result.risk_assessments if ra.risk_level == "critical"]
    assert len(critical_ras) >= 2

    classically_broken_status = {}
    for ra in critical_ras:
        det = next(det for det in scan_result.detections if det.id == ra.detection_id)
        classically_broken_status[ra.detection_id] = det.classically_broken

    assert any(classically_broken_status.values())
    assert any(v is False for v in classically_broken_status.values())
