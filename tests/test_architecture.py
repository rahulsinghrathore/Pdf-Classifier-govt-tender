"""CLAUDE.md's import rules, checked on the source: hard rules 3 and 17."""

from __future__ import annotations

import ast
from pathlib import Path

import tender_sections

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "tender_sections"
DETERMINISTIC = (
    "ingest",
    "boilerplate",
    "index_pages",
    "candidates",
    "scoring",
    "levels",
    "assemble",
    "validate",
    "labels",
    "ocr",
    "headings",
    "config",
    "models",
)


def imports(path: Path) -> list[tuple[str, tuple[str, ...]]]:
    """(module, imported names) of every import statement in the file."""
    found: list[tuple[str, tuple[str, ...]]] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found += [(alias.name, ()) for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.append((node.module, tuple(alias.name for alias in node.names)))
    return found


def test_deterministic_stages_never_import_the_llm():
    for stage in DETERMINISTIC:
        modules = [module for module, _ in imports(PACKAGE / f"{stage}.py")]
        assert not [m for m in modules if m.startswith("tender_sections.llm")], stage


def test_the_ui_uses_only_the_public_api():
    ours = [
        (module, names)
        for module, names in imports(ROOT / "app" / "streamlit_app.py")
        if module.split(".")[0] == "tender_sections"
    ]
    assert [module for module, _ in ours] == ["tender_sections"]
    assert set(ours[0][1]) <= set(tender_sections.__all__)
