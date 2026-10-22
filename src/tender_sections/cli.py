"""Command line (SPEC §12).

    python -m tender_sections extract tender.pdf [--no-llm] [--config YAML] [--full] [--debug]
    python -m tender_sections eval eval/labelled/ [--report eval/report.md]

stdout carries JSON only, so it can go to a file or to jq; warnings, errors and the --debug
candidate table go to stderr. Exit status 0; 2 when the result needs human review; 1 on an error,
bad arguments included, so that 2 always means review.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any, NoReturn

import pymupdf
import yaml

from tender_sections import extract
from tender_sections.config import Settings, load_settings
from tender_sections.llm import LLMNotConfigured
from tender_sections.models import Candidate

EXIT_OK, EXIT_ERROR, EXIT_REVIEW = 0, 1, 2


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return args.command(args)
    except (OSError, ValueError, yaml.YAMLError, pymupdf.FileDataError, LLMNotConfigured) as error:
        print(f"error: {_describe(error)}", file=sys.stderr)
        return EXIT_ERROR


def candidate_table(candidates: list[Candidate]) -> str:
    """One row per candidate in document order: stable text to diff before and after a change."""
    rows = [
        f"{'page':>4}  {'kind':<11}  {'score':>5}  {'decision':<9}  {'by':<13}  {'level':>5}  "
        f"{'label':<14}  text  [score breakdown]"
    ]
    for c in candidates:
        level = "-" if c.level is None else str(c.level)
        breakdown = " ".join(f"{key}={value:+d}" for key, value in c.score_breakdown.items())
        rows.append(
            f"{c.line.page:>4}  {c.kind:<11}  {c.score:>5}  {c.decision:<9}  "
            f"{c.decided_by or '-':<13}  {level:>5}  {c.label:<14}  {c.line.text}  [{breakdown}]"
        )
    return "\n".join(rows)


def _extract(args: argparse.Namespace) -> int:
    result = extract(args.pdf, _settings(args), debug=args.debug)
    if args.full:
        _emit(result.model_dump(mode="json", exclude=None if args.debug else {"debug"}))
    else:
        _emit({"targets": result.targets, "targets_status": result.targets_status})
    for warning in result.warnings:
        page = "" if warning.page is None else f" p{warning.page}"
        print(f"warning {warning.code}{page}: {warning.message}", file=sys.stderr)
    if args.debug and result.debug is not None:
        print(candidate_table(result.debug.candidates), file=sys.stderr)
    if result.needs_human_review:
        print("needs human review: a document-level check failed", file=sys.stderr)
        return EXIT_REVIEW
    return EXIT_OK


def _eval(args: argparse.Namespace) -> int:
    from tender_sections.evaluate import render_report, run_eval

    evaluation = run_eval(
        args.directory,
        _settings(args),
        on_document=lambda name: print(f"eval: {name}", file=sys.stderr),
    )
    for note in evaluation.skipped:
        print(f"skipped: {note}", file=sys.stderr)
    if not evaluation.documents:
        print(
            f"error: no labelled tenders in {args.directory} "
            "(want <name>.pdf next to <name>.expected.json)",
            file=sys.stderr,
        )
        return EXIT_ERROR
    if args.report is not None:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(render_report(evaluation), encoding="utf-8")
        print(f"report: {args.report}", file=sys.stderr)
    _emit(evaluation.summary())
    return EXIT_OK


def _settings(args: argparse.Namespace) -> Settings:
    settings = load_settings(args.config)
    if args.no_llm:
        llm = settings.llm.model_copy(update={"enabled": False})
        settings = settings.model_copy(update={"llm": llm})
    return settings


def _emit(payload: Any) -> None:
    sys.stdout.write(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def _describe(error: Exception) -> str:
    if isinstance(error, FileNotFoundError) and error.filename is None:
        return f"no such file: {error}"  # load_settings raises FileNotFoundError(path)
    return str(error)


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:  # exit 1, not argparse's 2: 2 means review
        self.print_usage(sys.stderr)
        self.exit(EXIT_ERROR, f"{self.prog}: error: {message}\n")


def _parser() -> argparse.ArgumentParser:
    parser = _Parser(
        prog="python -m tender_sections",
        description="Page ranges of business-defined sections in tender PDFs.",
    )
    commands = parser.add_subparsers(metavar="{extract,eval}", required=True)
    common = _Parser(add_help=False)
    common.add_argument(
        "--no-llm",
        action="store_true",
        help="reject the undecided band instead of asking the LLM; no fallback pass",
    )
    common.add_argument(
        "--config",
        type=Path,
        metavar="YAML",
        help="settings file (default: the code defaults); TENDER_* variables override it",
    )

    one = commands.add_parser("extract", parents=[common], help="extract one tender")
    one.add_argument("pdf", type=Path)
    one.add_argument("--full", action="store_true", help="print the whole result, not the targets")
    one.add_argument(
        "--debug",
        action="store_true",
        help="print the candidate table on stderr; with --full, add the debug block to the JSON",
    )
    one.set_defaults(command=_extract)

    many = commands.add_parser("eval", parents=[common], help="score against labelled tenders")
    many.add_argument("directory", type=Path, help="<name>.pdf files with <name>.expected.json")
    many.add_argument("--report", type=Path, metavar="MD", help="write a Markdown report here")
    many.set_defaults(command=_eval)
    return parser
