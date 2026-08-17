"""Command line entry point for the gloss trial."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from molcajete_prep.claude_status import print_batch_status
from molcajete_prep.epub import extract_chapters
from molcajete_prep.glossing.claude import ModelSettings
from molcajete_prep.lexicon import build_lexicon
from molcajete_prep.nlp import load_pipeline, tokenize_paragraphs
from molcajete_prep.trial import ARM_A, ARM_B, render_trial, run_trial


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gloss_trial.py",
        description=(
            "Gloss a stratified sample of a book with Claude, at two settings, "
            "and write both answers out for review. Writes no bundle and never "
            "touches the shared gloss cache."
        ),
    )
    parser.add_argument("epub", help="path to a DRM-free EPUB")
    parser.add_argument(
        "--limit", type=int, default=200, help="how many lemmas to gloss (default: 200)"
    )
    parser.add_argument("--out", help="write the report here instead of stdout")
    parser.add_argument(
        "--one-arm",
        action="store_true",
        help="run only the production setting, skipping the comparison arm",
    )
    parser.add_argument(
        "--split-on-heading",
        action="store_true",
        help="split each spine document on <h1>-<h6>",
    )
    parser.add_argument(
        "--keep-boilerplate",
        action="store_true",
        help="keep text outside Project Gutenberg's START/END markers",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    sources = extract_chapters(
        args.epub,
        split_on_heading=args.split_on_heading,
        keep_boilerplate=args.keep_boilerplate,
    )
    if not sources:
        raise SystemExit(f"{args.epub} yielded no chapters with prose in them")

    nlp = load_pipeline()
    chapters = [tokenize_paragraphs(nlp, list(source.paragraphs)) for source in sources]
    lexicon = build_lexicon(chapters)

    arms: tuple[ModelSettings, ...] = (ARM_A,) if args.one_arm else (ARM_A, ARM_B)
    print(
        f"Glossing {args.limit} of {len(lexicon.records):,} lemmas "
        f"across {len(arms)} arm(s)...",
        file=sys.stderr,
    )

    trial = run_trial(
        lexicon,
        chapters,
        size=args.limit,
        arms=arms,
        on_status=print_batch_status,
    )
    report = render_trial(trial, built_at=datetime.now())

    if args.out:
        path = Path(args.out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(report, encoding="utf-8")
        print(f"Wrote {path}  (~${trial.total_cost:.2f})", file=sys.stderr)
    else:
        print(report, end="")

    return 0


if __name__ == "__main__":
    sys.exit(main())
