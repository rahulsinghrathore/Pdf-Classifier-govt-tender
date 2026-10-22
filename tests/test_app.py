"""The Streamlit UI (SPEC §13), driven headless with AppTest: no browser, no network."""

from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

from helpers import F1, fixture_pdf
from pdfgen import Text, make_pdf, paragraph

APP = Path(__file__).resolve().parents[1] / "app" / "streamlit_app.py"
NIT = [Text(72, 100, "NOTICE INVITING TENDER", bold=True), *paragraph(140)]
PQC = [Text(72, 100, "PRE-QUALIFICATION CRITERIA", bold=True), *paragraph(140)]
UNSURE = [Text(72, 100, "Information for transporter / goods carrier", size=12, bold=True)]
UNSURE += paragraph(140)  # score 6: the LLM band
TENDER = make_pdf([NIT, PQC, paragraph(100)])


def uploaded(pdf: bytes = TENDER, name: str = "tender.pdf") -> AppTest:
    app = AppTest.from_file(str(APP), default_timeout=60).run()
    app.file_uploader(key="upload").upload(name, pdf, "application/pdf").run()
    return app


def extracted(pdf: bytes = TENDER, name: str = "tender.pdf") -> AppTest:
    app = uploaded(pdf, name)
    app.button(key="run").click().run()
    assert not app.exception
    return app


def test_the_page_asks_for_a_pdf_first():
    app = AppTest.from_file(str(APP), default_timeout=60).run()
    assert not app.exception
    assert [info.value for info in app.info] == ["Upload a tender PDF to begin."]


def test_nothing_runs_before_run_is_pressed():
    app = uploaded()
    assert [info.value for info in app.info] == ["Press Run to extract."]
    assert app.session_state.page == 1


def test_run_shows_the_targets_strip_and_the_tabs():
    app = extracted()
    pqc, scc = app.button(key="target_pqc"), app.button(key="target_scc")
    assert ("PQC" in pqc.label, "p2–3" in pqc.label, pqc.disabled) == (True, True, False)
    assert ("absent" in scc.label, scc.disabled) == (True, True)  # absent and unlisted
    assert [tab.label for tab in app.tabs] == ["Sections", "JSON", "Checks"]
    assert app.caption[0].value.startswith("ingest ✓ · boilerplate ✓ · index ✓ · scoring ✓")
    assert "llm (0) ✓" in app.caption[0].value


def test_go_buttons_and_tiles_move_the_viewer():
    app = extracted()
    app.button(key="go_pqc").click().run()
    assert (app.session_state.page, app.number_input(key="page").value) == (2, 2)
    app.button(key="next").click().run()
    assert app.session_state.page == 3
    app.button(key="target_pqc").click().run()
    assert app.session_state.page == 2
    app.button(key="prev").click().run()
    assert app.session_state.page == 1


def test_a_settings_change_needs_a_new_run():
    app = extracted()
    app.slider(key="accept").set_value(9).run()
    assert [info.value for info in app.info] == ["Settings changed: press Run again."]
    app.slider(key="accept").set_value(8).run()  # back to the settings already run: cached
    assert app.button(key="target_pqc").label


def test_crossed_thresholds_disable_run():
    app = uploaded()
    app.slider(key="reject").set_value(8).run()
    assert app.button(key="run").disabled
    assert app.sidebar.error[0].value == "The reject score must be below the accept score."


def test_debug_tab_lists_the_candidates():
    app = extracted()
    app.toggle(key="show_debug").set_value(True).run()
    assert [tab.label for tab in app.tabs] == ["Sections", "JSON", "Checks", "Debug"]
    candidates = app.dataframe[0].value
    assert {"NOTICE INVITING TENDER", "PRE-QUALIFICATION CRITERIA"} <= set(candidates["text"])


def test_a_document_for_review_says_so():
    app = extracted(make_pdf([[]]))
    assert any(error.value.startswith("Needs human review") for error in app.error)


def test_an_extraction_failure_is_shown_not_raised():
    # The LLM is on and a line is unsure, but tests cannot build the real client (conftest).
    app = uploaded(make_pdf([NIT, UNSURE]))
    app.toggle(key="llm").set_value(True).run()
    app.button(key="run").click().run()
    assert not app.exception
    assert any(error.value.startswith("Extraction failed") for error in app.error)


def test_downloads_are_named_after_the_file():
    app = extracted(name="PUR1011848.pdf")
    names = {button.proto.label for button in app.get("download_button")}
    assert names == {"targets.json", "sections.json", "full.json"}


def test_a_not_applicable_tile_names_the_page_that_says_so():
    app = extracted(fixture_pdf(F1).read_bytes(), "nrl_pur1011567.pdf")
    scc = app.button(key="target_scc")
    assert ("N/A" in scc.label, scc.help) == (True, "listed as Not Applicable on p15 (Annexure 20)")
    scc.click().run()
    assert app.session_state.page == 15
