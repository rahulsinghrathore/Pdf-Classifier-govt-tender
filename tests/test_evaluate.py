"""The evaluation harness (SPEC §15). On the fixtures it must find nothing wrong; perturbed truths
(in memory only: the fixture files are never edited) check that each error lands in its bucket."""

from __future__ import annotations

import copy
import json
from collections.abc import Callable
from typing import Any

import pytest

from helpers import F1, F2, FIXTURE_NAMES, expected, result
from pdfgen import Text, make_pdf, paragraph
from tender_sections.cli import main
from tender_sections.evaluate import Truth, score_document

BAND = {F1: 1, F2: 12}  # undecided candidates (SPEC §5c), rejected with the LLM off


def perturbed(name: str, change: Callable[[dict[str, Any]], None]) -> Truth:
    data = copy.deepcopy(expected(name))
    change(data)
    return Truth.parse(data)


def buckets(name: str, truth: Truth, **changes: Any) -> list[tuple[str, int | None]]:
    mine = result(name).model_copy(update=changes) if changes else result(name)
    return [(error.bucket, error.page) for error in score_document(name, mine, truth).errors]


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_the_fixtures_score_perfectly(name):
    score = score_document(name, result(name), Truth.parse(expected(name)))
    assert score.errors == []
    assert list(score.targets.values()) == [(True, True)] * 5
    assert all(right == total > 0 for right, total in score.starts.values())
    assert all(right == emitted == want > 0 for right, emitted, want in score.found.values())
    assert score.nesting[0] == score.nesting[1] == len(Truth.parse(expected(name)).levels)
    assert score.false_headings == (0, len(expected(name)["flat_inclusive"]))
    assert (score.llm_calls, score.band[0]) == (0, BAND[name])


def test_f1_lettered_sections_take_their_level_from_level1_titles():
    truth = Truth.parse(expected(F1))
    assert {key: truth.levels[key] for key in ("checklist", "pqc", "atc", "annexure_list")} == {
        "checklist": 1,
        "pqc": 1,
        "atc": 1,
        "annexure_list": 1,
    }
    # The orphan Annexure 7.2 hangs under D, not under Annexure 6 (CLAUDE.md hard rule 1).
    assert truth.parents()["annexure_7_2"] == "annexure_list"


def test_a_wrong_level_is_a_level_error():
    truth = perturbed(F2, lambda data: data["tree_levels"].update(annexure_19=3))
    assert buckets(F2, truth) == [("level", 58)]


def test_a_heading_on_an_index_page_that_is_no_section_is_an_index_page_error():
    # Pretend f1's "D. TENDER ANNEXURES" (p14, an index page) were not a section.
    truth = perturbed(F1, lambda data: data["flat_inclusive"].pop("annexure_list"))
    errors = score_document(F1, result(F1), truth).errors
    assert [(e.bucket, e.page) for e in errors if e.what.startswith("annexure_list")] == [
        ("index_page", 14)
    ]


def test_a_section_missed_on_a_drawing_page_is_an_ocr_error():
    truth = perturbed(F2, lambda data: data["flat_inclusive"].update(annexure_22=[84, 85]))
    assert buckets(F2, truth) == [("ocr", 84)]


def test_a_target_resolved_to_the_wrong_section_is_a_label_error():
    # The truth says SOR is Annexure 20's range: the section is found, the label is not on it.
    truth = perturbed(F2, lambda data: data["targets"].update(sor=[69, 78]))
    assert buckets(F2, truth) == [("label", 69)]


def test_a_missed_not_applicable_listing_is_an_index_page_error():
    status = {**result(F1).targets_status, "scc": "absent"}
    assert buckets(F1, Truth.parse(expected(F1)), targets_status=status) == [("index_page", None)]


# The command line ---------------------------------------------------------------------------------

NIT = [Text(72, 100, "NOTICE INVITING TENDER", bold=True), *paragraph(140)]
PQC = [Text(72, 100, "PRE-QUALIFICATION CRITERIA", bold=True), *paragraph(140)]
TRUTH = {
    "targets": {"pqc": [2, 2], "atc": None, "scc": None, "sor": None, "tech_spec": None},
    "targets_status": {
        "pqc": "found",
        "atc": "absent",
        "scc": "absent",
        "sor": "absent",
        "tech_spec": "absent",
    },
    "flat_inclusive": {"nit": [1, 1], "pqc": [2, 2]},
    "tree_levels": {"nit": 1, "pqc": 1},
}


def test_eval_scores_a_folder_and_writes_the_report(tmp_path, capsys):
    (tmp_path / "t1.pdf").write_bytes(make_pdf([NIT, PQC]))
    (tmp_path / "t1.expected.json").write_text(json.dumps(TRUTH))
    (tmp_path / "unlabelled.pdf").write_bytes(make_pdf([NIT]))
    (tmp_path / "orphan.expected.json").write_text(json.dumps(TRUTH))
    report = tmp_path / "out" / "report.md"
    code = main(["eval", str(tmp_path), "--no-llm", "--report", str(report)])
    out, err = capsys.readouterr()
    summary = json.loads(out)
    assert code == 0
    assert (summary["documents"], summary["targets"]["range"], summary["section_f1"]["1"]) == (
        1,
        1.0,
        1.0,
    )
    assert "skipped: unlabelled.pdf: no unlabelled.expected.json" in err
    assert "skipped: orphan.expected.json: no orphan.pdf" in err
    text = report.read_text(encoding="utf-8")
    assert text.startswith("# Evaluation report")
    assert "| target ranges exactly right | 5/5 (100%) |" in text
    assert "No errors." in text


def test_eval_without_labelled_tenders_is_an_error(tmp_path, capsys):
    assert main(["eval", str(tmp_path), "--no-llm"]) == 1
    assert "no labelled tenders" in capsys.readouterr().err
    assert main(["eval", str(tmp_path / "missing"), "--no-llm"]) == 1


def test_eval_rejects_a_truth_without_its_required_keys(tmp_path, capsys):
    (tmp_path / "t1.pdf").write_bytes(make_pdf([NIT]))
    (tmp_path / "t1.expected.json").write_text(json.dumps({"targets": {}}))
    assert main(["eval", str(tmp_path), "--no-llm"]) == 1
    assert "t1.expected.json has no targets_status, flat_inclusive" in capsys.readouterr().err
