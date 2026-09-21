"""Tests for ``ecdat rules`` and ``ecdat explain`` (Phase 76, Task B3).

Covers the real ``ecdat_core.signature_loader`` API usage: filtering, the
human-readable table, the ``--json`` payload, single/multiple/no-match
``explain`` behaviour, and markup-safety of untrusted query text.
"""

from __future__ import annotations

import json

import pytest

from ecdat.cli.commands import explain as explain_cmd
from ecdat.cli.commands import rules as rules_cmd
from ecdat.cli.main import main
from ecdat_core.signature_loader import get_all_signatures


@pytest.fixture(autouse=True)
def _wide_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force a wide, deterministic Rich layout regardless of the test runner."""
    monkeypatch.setenv("COLUMNS", "200")


class _RulesArgs:
    def __init__(
        self,
        query: str | None = None,
        family: str | None = None,
        language: str | None = None,
        json: bool = False,
    ) -> None:
        self.query = query
        self.family = family
        self.language = language
        self.json = json


class _ExplainArgs:
    def __init__(self, name: str) -> None:
        self.name = name


# ---- rules ----------------------------------------------------------------


def test_rules_rsa_returns_rows(capsys: pytest.CaptureFixture[str]) -> None:
    rc = rules_cmd.run(_RulesArgs(query="rsa"))
    out = capsys.readouterr().out
    assert rc == 0
    assert "1 of 15 signatures" in out
    assert "RSA" in out
    assert "ML-KEM" in out
    assert "asymmetric" in out


def test_rules_is_case_insensitive(capsys: pytest.CaptureFixture[str]) -> None:
    rc = rules_cmd.run(_RulesArgs(query="RSA"))
    assert rc == 0
    assert "RSA" in capsys.readouterr().out


def test_rules_family_filter(capsys: pytest.CaptureFixture[str]) -> None:
    rc = rules_cmd.run(_RulesArgs(family="hash"))
    out = capsys.readouterr().out
    assert rc == 0
    assert "2 of 15 signatures" in out
    assert "MD5" in out
    assert "SHA-1" in out
    assert "RSA" not in out


def test_rules_language_filter(capsys: pytest.CaptureFixture[str]) -> None:
    rc = rules_cmd.run(_RulesArgs(language="go"))
    out = capsys.readouterr().out
    assert rc == 0
    assert "15 of 15 signatures" in out


def test_rules_no_match_is_friendly_and_zero(
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = rules_cmd.run(_RulesArgs(query="zzzz"))
    out = capsys.readouterr().out
    assert rc == 0
    assert "No signatures match" in out
    assert "0 of 15" in out


def test_rules_json_parses(capsys: pytest.CaptureFixture[str]) -> None:
    rc = rules_cmd.run(_RulesArgs(query="rsa", json=True))
    out = capsys.readouterr().out
    assert rc == 0
    payload = json.loads(out)
    assert isinstance(payload, list)
    assert len(payload) == 1
    item = payload[0]
    assert item["name"] == "RSA"
    assert item["quantum_vulnerable"] is True
    assert item["classically_broken"] is False
    assert item["recommended_algorithm"]
    assert sorted(item["languages"]) == item["languages"]


def test_rules_json_reflects_filters(capsys: pytest.CaptureFixture[str]) -> None:
    rc = rules_cmd.run(_RulesArgs(family="hash", json=True))
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert {p["name"] for p in payload} == {"MD5", "SHA-1"}


def test_rules_json_is_valid_when_empty(capsys: pytest.CaptureFixture[str]) -> None:
    rc = rules_cmd.run(_RulesArgs(query="zzzz", json=True))
    assert rc == 0
    assert json.loads(capsys.readouterr().out) == []


def test_rules_total_matches_knowledge_base(
    capsys: pytest.CaptureFixture[str],
) -> None:
    total = len(get_all_signatures())
    rc = rules_cmd.run(_RulesArgs())
    out = capsys.readouterr().out
    assert rc == 0
    assert f"{total} of {total} signatures" in out


# ---- explain --------------------------------------------------------------


def test_explain_rsa_mentions_shor(capsys: pytest.CaptureFixture[str]) -> None:
    rc = explain_cmd.run(_ExplainArgs("rsa"))
    out = capsys.readouterr().out
    assert rc == 0
    assert "RSA" in out
    assert "Shor" in out
    assert "ML-KEM" in out
    assert "FIPS 203" in out


def test_explain_is_case_insensitive(capsys: pytest.CaptureFixture[str]) -> None:
    rc = explain_cmd.run(_ExplainArgs("RSA"))
    assert rc == 0
    assert "Shor" in capsys.readouterr().out


def test_explain_aes_reports_grover_threshold(
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = explain_cmd.run(_ExplainArgs("aes"))
    out = capsys.readouterr().out
    assert rc == 0
    assert "Grover" in out
    assert "192-bit" in out


def test_explain_md5_shows_classical_warning(
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = explain_cmd.run(_ExplainArgs("md5"))
    out = capsys.readouterr().out
    assert rc == 0
    assert "MD5" in out
    assert "classical" in out.lower()
    assert "Warning" in out


def test_explain_md5_not_reported_as_quantum_safe(
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = explain_cmd.run(_ExplainArgs("md5"))
    out = capsys.readouterr().out
    assert rc == 0
    assert "do not treat it as quantum-safe" in out


def test_explain_shows_mosca_and_languages(
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = explain_cmd.run(_ExplainArgs("ecdsa"))
    out = capsys.readouterr().out
    assert rc == 0
    assert "Mosca" in out
    assert "X + Y > Z" in out
    assert "python" in out
    assert "ML-DSA" in out


def test_explain_unknown_suggests_close_match(
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = explain_cmd.run(_ExplainArgs("rsq"))
    out = capsys.readouterr().out
    assert rc == 2
    assert "Did you mean" in out
    assert "RSA" in out


def test_explain_unknown_without_suggestions_exits_2(
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = explain_cmd.run(_ExplainArgs("zzzz"))
    out = capsys.readouterr().out
    assert rc == 2
    assert "No signature named" in out


def test_explain_multiple_matches_lists_and_exits_2(
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = explain_cmd.run(_ExplainArgs("signature"))
    out = capsys.readouterr().out
    assert rc == 2
    assert "be more specific" in out
    assert "ECDSA" in out
    assert "DSA" in out


def test_explain_hostile_name_is_literal_not_markup(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A hostile query must render literally — never parsed as Rich markup."""
    hostile = "[bold red]x[/]"
    rc = explain_cmd.run(_ExplainArgs(hostile))
    out = capsys.readouterr().out
    assert rc == 2
    assert hostile in out


# ---- dispatch through main() ---------------------------------------------


def test_main_dispatches_rules(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["rules", "rsa"])
    assert rc == 0
    assert "RSA" in capsys.readouterr().out


def test_main_dispatches_explain(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["explain", "rsa"])
    assert rc == 0
    assert "Shor" in capsys.readouterr().out


def test_main_rules_json_only_payload(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["rules", "--json", "rsa"])
    out = capsys.readouterr().out
    assert rc == 0
    assert json.loads(out)[0]["name"] == "RSA"
