"""Command line entry point for the gloss trial."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from molcajete_book.cli import CACHE_DIR
from molcajete_book.epub import extract_chapters
from molcajete_prep.claude_status import print_batch_status
from molcajete_prep.glossing.provider import (
    CLAUDE,
    OLLAMA,
    PROVIDER_NAMES,
    GlossProvider,
    ProviderOptions,
    build_provider,
)
from molcajete_prep.lexicon import build_lexicon
from molcajete_prep.nlp import load_pipeline, tokenize_paragraphs
from molcajete_prep.trial import (
    ARM_A,
    ARM_B,
    DEFAULT_GOLD_PATH,
    claude_arms,
    load_gold,
    render_trial,
    run_trial,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gloss_trial.py",
        description=(
            "Gloss a stratified sample of a book and write the answers out for "
            "review. Writes no bundle and never touches the shared gloss cache."
        ),
    )
    parser.add_argument("epub", help="path to a DRM-free EPUB")
    parser.add_argument(
        "--limit", type=int, default=200, help="how many lemmas to gloss (default: 200)"
    )
    parser.add_argument("--out", help="write the report here instead of stdout")
    parser.add_argument(
        "--provider",
        choices=PROVIDER_NAMES,
        default=CLAUDE,
        help=f"which provider to audition (default: {CLAUDE})",
    )
    parser.add_argument(
        "--model",
        help="override the provider's model. With --provider ollama, may be "
        "given more than once to compare models side by side.",
        action="append",
    )
    parser.add_argument(
        "--gold",
        default=str(DEFAULT_GOLD_PATH),
        help="a list of lemmas known to be Mexican, one per line. Scores "
        "mexicanism recall over the ones this book actually contains. "
        "Defaults to the list shipped with molcajete-prep.",
    )
    parser.add_argument(
        "--one-arm",
        action="store_true",
        help="Claude only: run just the production setting, skipping the "
        "comparison arm",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=ProviderOptions.concurrency,
        help=f"local only: requests in flight (default: {ProviderOptions.concurrency})",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=ProviderOptions.retries,
        help=f"local only: stricter re-asks after a bad answer (default: "
        f"{ProviderOptions.retries})",
    )
    parser.add_argument(
        "--chunk",
        type=int,
        help="lemmas per request. Defaults to 25 for Claude and 1 locally.",
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


def arms_for(args: argparse.Namespace) -> list[tuple[str, GlossProvider]]:
    """One arm per thing being compared.

    For Claude that is two settings of one model, because the open question
    there was whether thinking earns its output tokens. For Ollama it is one
    arm per model named, because the open question is which local model is
    usable at all.
    """
    if args.provider == CLAUDE:
        settings = (ARM_A,) if args.one_arm else (ARM_A, ARM_B)
        return claude_arms(*settings)

    models = args.model or [None]
    return [
        (
            name or "default",
            build_provider(
                ProviderOptions(
                    name=OLLAMA,
                    model=name,
                    chunk_size=args.chunk,
                    concurrency=args.concurrency,
                    retries=args.retries,
                )
            ),
        )
        for name in models
    ]


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

    gold = load_gold(args.gold) if args.gold else []
    arms = arms_for(args)
    print(
        f"Glossing {args.limit} of {len(lexicon.records):,} lemmas "
        f"across {len(arms)} arm(s)"
        + (f", scoring {len(gold)} gold lemmas" if gold else "")
        + "...",
        file=sys.stderr,
    )
    for label, provider in arms:
        print(f"  arm {label}: {provider.describe()}", file=sys.stderr)

    trial = run_trial(
        lexicon,
        chapters,
        size=args.limit,
        providers=arms,
        gold=gold,
        extract_dir=CACHE_DIR / "kaikki",
        on_status=print_batch_status,
    )
    report = render_trial(trial, built_at=datetime.now(), lexicon=lexicon)

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
