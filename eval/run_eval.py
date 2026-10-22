"""The evaluation harness as a script (SPEC §15); the same as `python -m tender_sections eval`.

python eval/run_eval.py eval/labelled --report eval/report.md [--no-llm] [--config YAML]
"""

import sys

from tender_sections.cli import main

if __name__ == "__main__":
    sys.exit(main(["eval", *sys.argv[1:]]))
