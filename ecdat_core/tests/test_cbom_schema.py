"""Validate ECDAT's exported CBOM against the official CycloneDX 1.6 JSON Schema.

The official schema files (``bom-1.6.schema.json`` and its two external
references ``jsf-0.82.schema.json`` / ``spdx.schema.json``) are vendored
unmodified under ``fixtures/cyclonedx/`` so this test runs fully offline
and deterministically.

This is the project's strongest structural claim about its CBOM output:
it conforms to the actual published CycloneDX 1.6 spec, not merely to
hand-written spot checks.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft7Validator, FormatChecker, ValidationError
from referencing import Registry, Resource

from ecdat_core.cbom_export import export_cbom
from ecdat_core.cli import run_scan

_SCHEMA_DIR = Path(__file__).parent / "fixtures" / "cyclonedx"

_BOM_SCHEMA = json.loads((_SCHEMA_DIR / "bom-1.6.schema.json").read_text())
_JSF_SCHEMA = json.loads((_SCHEMA_DIR / "jsf-0.82.schema.json").read_text())
_SPDX_SCHEMA = json.loads((_SCHEMA_DIR / "spdx.schema.json").read_text())

_FIXTURE_DEMO_REPO = Path(__file__).parent / "fixtures" / "demo_repo"
_FIXTURE_SHOWCASE_REPO = Path(__file__).parent / "fixtures" / "showcase_repo"

_SCHEMA_BASE_URI = "http://cyclonedx.org/schema/"

# The official BOM schema references jsf-0.82.schema.json and spdx.schema.json
# over HTTPS; validation must stay offline and deterministic, so both external
# documents are supplied here from the local vendored copies.
_REGISTRY = (
    Registry()
    .with_resource(
        _SCHEMA_BASE_URI + "jsf-0.82.schema.json",
        Resource.from_contents(_JSF_SCHEMA),
    )
    .with_resource(
        _SCHEMA_BASE_URI + "spdx.schema.json",
        Resource.from_contents(_SPDX_SCHEMA),
    )
)


def _build_validator() -> Draft7Validator:
    """Return a Draft7 validator wired to the vendored official schema.

    Format assertions (RFC 3339 ``date-time`` timestamps) are enforced via
    ``FormatChecker`` so validation is as strict as real CycloneDX tooling.
    """
    return Draft7Validator(
        _BOM_SCHEMA,
        registry=_REGISTRY,
        format_checker=FormatChecker(),
    )


def _validate_cbom(cbom: dict) -> None:
    """Assert *cbom* conforms to the official CycloneDX 1.6 JSON Schema."""
    errors = sorted(
        _build_validator().iter_errors(cbom),
        key=lambda err: (list(err.absolute_path), err.message),
    )
    if errors:
        detail = "\n".join(
            f"  - {'/'.join(str(p) for p in err.absolute_path) or '<root>'}: "
            f"{err.message}"
            for err in errors[:20]
        )
        raise AssertionError(
            f"CBOM failed official CycloneDX 1.6 schema validation "
            f"({len(errors)} error(s)):\n{detail}"
        )


def test_vendored_schema_is_official_cyclonedx_16() -> None:
    """Sanity-check the vendored schema is the real CycloneDX 1.6 schema."""
    assert _BOM_SCHEMA["$id"] == "http://cyclonedx.org/schema/bom-1.6.schema.json"
    assert _BOM_SCHEMA["$schema"] == "http://json-schema.org/draft-07/schema#"
    assert _BOM_SCHEMA["title"] == "CycloneDX Bill of Materials Standard"
    component_types = (
        _BOM_SCHEMA["definitions"]["component"]["properties"]["type"]["enum"]
    )
    assert "cryptographic-asset" in component_types
    asset_types = _BOM_SCHEMA["definitions"]["cryptoProperties"]["properties"][
        "assetType"
    ]["enum"]
    assert asset_types == [
        "algorithm",
        "certificate",
        "protocol",
        "related-crypto-material",
    ]


@pytest.fixture(scope="module")
def demo_scan_result():
    """Run a real scan over the demo_repo fixture once for the whole module."""
    return run_scan(str(_FIXTURE_DEMO_REPO))


@pytest.fixture(scope="module")
def showcase_scan_result():
    """Run a real scan over the showcase_repo fixture once for the whole module.

    The showcase repo is the wide-coverage fixture (DH/ECDH key agreement,
    ML-KEM, ML-DSA, SLH-DSA, RSA, hashes, block ciphers) whose live scan is
    the one used in the demo; validating its CBOM covers the primitive enum
    paths demo_repo does not exercise.
    """
    return run_scan(str(_FIXTURE_SHOWCASE_REPO))


def test_real_scan_cbom_validates_against_official_schema(demo_scan_result) -> None:
    """A CBOM produced from an actual scan conforms to the official schema."""
    cbom = export_cbom(demo_scan_result)
    _validate_cbom(cbom)


def test_showcase_scan_cbom_validates_against_official_schema(
    showcase_scan_result,
) -> None:
    """The wide-coverage showcase CBOM conforms to the official schema."""
    cbom = export_cbom(showcase_scan_result)
    _validate_cbom(cbom)


def test_cbom_boolean_properties_are_lowercase(demo_scan_result) -> None:
    """Every component's boolean ecdat: properties use lowercase values."""
    cbom = export_cbom(demo_scan_result)
    for component in cbom["components"]:
        props = {p["name"]: p["value"] for p in component["properties"]}
        assert props["ecdat:quantumVulnerable"] in {"true", "false"}
        assert props["ecdat:classicallyBroken"] in {"true", "false"}


def test_cbom_primitive_values_are_schema_members(demo_scan_result) -> None:
    """primitive values must be drawn from the official 1.6 enum."""
    valid_primitives = set(
        _BOM_SCHEMA["definitions"]["cryptoProperties"]["properties"][
            "algorithmProperties"
        ]["properties"]["primitive"]["enum"]
    )
    cbom = export_cbom(demo_scan_result)
    for component in cbom["components"]:
        alg_props = component.get("cryptoProperties", {}).get("algorithmProperties")
        if alg_props is not None:
            assert alg_props["primitive"] in valid_primitives


def test_validator_detects_a_known_violation(demo_scan_result) -> None:
    """The validator itself is trustworthy: a malformed BOM must fail."""
    bad = export_cbom(demo_scan_result)
    bad["bomFormat"] = "NotCycloneDX"
    with pytest.raises((ValidationError, AssertionError)):
        _validate_cbom(bad)