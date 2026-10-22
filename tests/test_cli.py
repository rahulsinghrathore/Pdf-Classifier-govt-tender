"""The command line (SPEC §12): JSON on stdout, warnings on stderr, exit 0 / 2 (review) / 1."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import anthropic
import dotenv
import pytest

from conftest import REAL_ANTHROPIC_INIT
from helpers import FIXTURE_NAMES, expected, fixture_pdf
from pdfgen import Text, make_pdf, paragraph
from tender_sections.cli import main
from tender_sections.llm.client import AnthropicClient

NIT = [Text(72, 100, "NOTICE INVITING TENDER", bold=True), *paragraph(140)]
PQC = [Text(72, 100, "PRE-QUALIFICATION CRITERIA", bold=True), *paragraph(140)]
UNSURE = [Text(72, 100, "Information for transporter / goods carrier", size=12, bold=True)]
UNSURE += paragraph(140)  # score 6: the LLM band


@pytest.fixture
def tender(tmp_path: Path) -> Path:
    path = tmp_path / "tender.pdf"
    path.write_bytes(make_pdf([NIT, PQC]))
    return path


def run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str, str]:
    code = main(list(argv))
    out, err = capsys.readouterr()
    return code, out, err


def test_extract_prints_the_targets(tender, capsys):
    code, out, _ = run(capsys, "extract", str(tender), "--no-llm")
    payload = json.loads(out)
    assert (code, list(payload)) == (0, ["targets", "targets_status"])
    assert payload["targets"]["pqc"] == [2, 2]
    assert payload["targets_status"]["scc"] == "absent"


def test_full_prints_the_whole_result_and_debug_only_when_asked(tender, capsys):
    _, out, _ = run(capsys, "extract", str(tender), "--no-llm", "--full")
    payload = json.loads(out)
    assert payload["flat_inclusive"] == {"nit": [1, 1], "pqc": [2, 2]}
    assert "debug" not in payload
    _, out, _ = run(capsys, "extract", str(tender), "--no-llm", "--full", "--debug")
    assert json.loads(out)["debug"]["candidates"]


def test_debug_writes_the_candidate_table_on_stderr(tender, capsys):
    _, out, err = run(capsys, "extract", str(tender), "--no-llm", "--debug")
    assert list(json.loads(out)) == ["targets", "targets_status"]  # stdout stays parseable
    rows = err.splitlines()
    assert rows[0].split()[:3] == ["page", "kind", "score"]
    page, kind, score, decision, by, level = next(
        row for row in rows if "NOTICE INVITING TENDER" in row
    ).split()[:6]
    assert (page, kind, decision, by, level) == ("1", "titled", "accept", "rules", "1")
    assert int(score) >= 8


def test_a_document_for_review_exits_2(tmp_path, capsys):
    blank = tmp_path / "blank.pdf"
    blank.write_bytes(make_pdf([[]]))
    code, out, err = run(capsys, "extract", str(blank), "--no-llm")
    assert code == 2
    assert json.loads(out)["targets_status"]["pqc"] == "absent"
    assert "warning NO_SECTIONS" in err and "needs human review" in err


def test_warnings_go_to_stderr_with_their_page(tmp_path, capsys):
    path = tmp_path / "unsure.pdf"
    path.write_bytes(make_pdf([NIT, UNSURE]))
    code, _, err = run(capsys, "extract", str(path), "--no-llm")
    assert code == 0
    assert "warning UNDECIDED_WITHOUT_LLM" in err


@pytest.mark.parametrize("argv", [[], ["extract"], ["extract", "a.pdf", "--bogus"], ["fetch"]])
def test_usage_errors_exit_1_because_2_means_review(argv, capsys):
    with pytest.raises(SystemExit) as exited:
        main(argv)
    assert exited.value.code == 1


def test_unreadable_input_is_an_error(tmp_path, capsys):
    code, out, err = run(capsys, "extract", str(tmp_path / "missing.pdf"), "--no-llm")
    assert (code, out) == (1, "")
    assert err.startswith("error:") and "missing.pdf" in err
    notes = tmp_path / "notes.pdf"
    notes.write_text("not a pdf")
    code, out, err = run(capsys, "extract", str(notes), "--no-llm")
    assert (code, out) == (1, "")
    assert err.startswith("error:")


def test_a_config_file_is_applied_and_checked(tender, tmp_path, capsys):
    config = tmp_path / "config.yaml"
    config.write_text("labels:\n  target_labels: [nit]\n")
    _, out, _ = run(capsys, "extract", str(tender), "--no-llm", "--config", str(config))
    assert json.loads(out)["targets"] == {"nit": [1, 1]}
    config.write_text("scoring:\n  no_such_weight: 1\n")
    code, out, err = run(capsys, "extract", str(tender), "--config", str(config))
    assert (code, out) == (1, "")
    assert "no_such_weight" in err
    code, _, err = run(capsys, "extract", str(tender), "--config", str(tmp_path / "none.yaml"))
    assert code == 1 and "no such file" in err


def test_a_missing_api_key_is_a_clear_error(tmp_path, monkeypatch, capsys):
    class Keyless:  # stands in for anthropic.Anthropic, so nothing here can reach the network
        api_key = auth_token = None

        def __init__(self, **kwargs: object) -> None:
            pass

    monkeypatch.setattr(AnthropicClient, "__init__", REAL_ANTHROPIC_INIT)
    monkeypatch.setattr(anthropic, "Anthropic", Keyless)
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *args, **kwargs: False)  # keep .env out
    monkeypatch.setenv("TENDER_LLM__ENABLED", "true")
    path = tmp_path / "unsure.pdf"
    path.write_bytes(make_pdf([NIT, UNSURE]))
    code, out, err = run(capsys, "extract", str(path))
    assert (code, out) == (1, "")
    assert "ANTHROPIC_API_KEY is not set" in err and "--no-llm" in err


def test_python_dash_m_writes_nothing_but_json(tender):
    src = Path(__file__).resolve().parents[1] / "src"
    done = subprocess.run(
        [sys.executable, "-m", "tender_sections", "extract", str(tender), "--no-llm"],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(src)},
    )
    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout)["targets"]["pqc"] == [2, 2]


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_fixture_targets_from_the_command_line(name, capsys):
    code, out, _ = run(capsys, "extract", str(fixture_pdf(name)), "--no-llm")
    targets = {k: v for k, v in expected(name)["targets"].items() if not k.startswith("_")}
    assert code == 0
    assert json.loads(out) == {
        "targets": targets,
        "targets_status": expected(name)["targets_status"],
    }
