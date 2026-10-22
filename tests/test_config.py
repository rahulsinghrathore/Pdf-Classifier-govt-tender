"""Settings (SPEC §11) and the structural heading patterns they carry (SPEC §5b)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from tender_sections.config import Settings, load_settings

ROOT = Path(__file__).resolve().parents[1]


def test_config_yaml_matches_code_defaults():
    assert load_settings(ROOT / "config.yaml") == Settings()


def test_environment_overrides_yaml(tmp_path, monkeypatch):
    path = tmp_path / "config.yaml"
    path.write_text("boilerplate:\n  min_pages: 5\n  top_band: 0.2\n", encoding="utf-8")
    monkeypatch.setenv("TENDER_BOILERPLATE__MIN_PAGES", "4")
    settings = load_settings(path)
    assert (settings.boilerplate.min_pages, settings.boilerplate.top_band) == (4, 0.2)
    assert settings.boilerplate.bottom_band == 0.90  # untouched keys keep their defaults


def test_unknown_keys_are_rejected(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("boilerplate:\n  min_page: 5\n", encoding="utf-8")
    with pytest.raises(ValidationError):
        load_settings(path)


def test_missing_config_file_is_an_error(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_settings(tmp_path / "missing.yaml")


@pytest.mark.parametrize(
    ("text", "groups"),
    [
        ("Annexure 19", ("Annexure", "19", "")),
        ("ANNEXURE-14.1 on Bidder's Letterhead", ("ANNEXURE", "14.1", "on Bidder's Letterhead")),
        ("PART–I: UNPRICED BID", ("PART", "I", "UNPRICED BID")),
        ("Annexure 2.6.1", ("Annexure", "2.6.1", "")),
        ("Section-IV Special Conditions", ("Section", "IV", "Special Conditions")),
    ],
)
def test_named_pattern_matches(text, groups):
    match = re.match(Settings().patterns.named, text)
    assert match is not None and match.groups() == groups


@pytest.mark.parametrize(
    "text", ["SCHEDULE OF RATES", "as per Annexure 8 enclosed", "Section Civil Works", "Formation"]
)
def test_named_pattern_rejects(text):
    assert re.match(Settings().patterns.named, text) is None


def test_letter_pattern_is_upper_case_only():
    letter = Settings().patterns.letter
    assert re.match(letter, "B. PRE-QUALIFICATION CRITERIA (PQC)").groups() == (
        "B",
        "PRE-QUALIFICATION CRITERIA (PQC)",
    )
    assert re.match(letter, "a) the bidder shall submit") is None
