"""Command line entry point for the prep pipeline."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from molcajete_book.bundle import build_bundle, write_bundle
from molcajete_book.report import render_report
from molcajete_prep.claude_status import print_batch_status
from molcajete_prep.glossing.cache import DEFAULT_CACHE_DIR
from molcajete_prep.classify import ClassificationOptions
from molcajete_prep.glossing.pipeline import CONTEXT_ONLY, VERBATIM, GlossingOptions
from molcajete_prep.glossing.provider import CLAUDE, PROVIDER_NAMES, ProviderOptions

BUNDLE_SUFFIX = ".molcajete.json"
REPORT_SUFFIX = ".report.txt"

# The gloss cache and the kaikki extracts live in molcajete-prep's own default
# location, `$XDG_CACHE_HOME/molcajete-prep/`, and no longer inside this repo.
#
# They moved when Rocola became the second consumer. What is in there — 11,764
# Wiktionary rows, 4,843 model glosses and 2.9 GB of extracts — is data about
# Spanish, belonging to the package rather than to either repo that reads it,
# and a per-repo copy means re-downloading the extracts and re-inferring glosses
# that already exist next door. At the measured 0.19 lemmas/sec that is hours.
#
# A cold build is now `rm -rf "$(python -c 'from molcajete_prep.glossing.cache
# import DEFAULT_CACHE_DIR; print(DEFAULT_CACHE_DIR)')"`, or simply
# `--cache-dir` pointed somewhere empty — which is the better habit anyway,
# since it leaves the shared cache alone.
CACHE_DIR = DEFAULT_CACHE_DIR



def load_known_lemmas(path: str | Path | None) -> frozenset[str]:
    """Read a `known.json` — the flat array of lemma strings from SPEC §8."""
    if path is None:
        return frozenset()
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"{path}: expected a flat array of lemma strings")
    return frozenset(str(lemma).lower() for lemma in data)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="build_bundle.py",
        description="Turn a DRM-free Spanish EPUB into a Molcajete bundle.",
    )
    parser.add_argument("epub", help="path to a DRM-free EPUB")
    parser.add_argument(
        "--out",
        default="../bundles",
        help="directory to write the bundle and report into (default: ../bundles)",
    )
    parser.add_argument("--book-id", help="override the generated book id")
    parser.add_argument("--title", help="override the title from EPUB metadata")
    parser.add_argument("--author", help="override the author from EPUB metadata")
    parser.add_argument(
        "--known",
        help="path to a known.json of already-known lemma strings",
    )
    parser.add_argument(
        "--split-on-heading",
        action="store_true",
        help="split each spine document on <h1>-<h6>, for editions that pack "
        "several chapters into one file",
    )
    parser.add_argument(
        "--keep-boilerplate",
        action="store_true",
        help="keep text outside Project Gutenberg's START/END markers, which is "
        "otherwise stripped as licence text",
    )
    parser.add_argument(
        "--include-documents",
        nargs="+",
        metavar="GLOB",
        help="keep only the spine documents whose filename matches one of these "
        "globs, e.g. 'PrimeraParte*' 'SegundaParte*'. For critical editions, "
        "where the introduction, notes and bibliography are as long as the "
        "novel and would otherwise become chapters and vocabulary.",
    )
    parser.add_argument(
        "--exclude-documents",
        nargs="+",
        metavar="GLOB",
        help="drop the spine documents whose filename matches one of these "
        "globs. Applied after --include-documents.",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="indent the JSON for reading by eye (larger file)",
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="print the report to stdout and write nothing",
    )
    parser.add_argument(
        "--max-cards",
        type=int,
        default=ClassificationOptions.max_cards_per_session,
        help="session cap used for the over-cap diagnostic (default: 18)",
    )
    parser.add_argument(
        "--zipf-threshold",
        type=float,
        default=ClassificationOptions.zipf_threshold,
        help="teach any lemma at or above this Zipf frequency (default: 3.5)",
    )
    parser.add_argument(
        "--min-book-count",
        type=int,
        default=ClassificationOptions.min_book_count,
        help="teach any lemma occurring at least this often (default: 3)",
    )

    glossing = parser.add_argument_group("glossing")
    glossing.add_argument(
        "--no-gloss",
        action="store_true",
        help="skip glossing entirely. Leaves de/en empty and mexicanism false, "
        "which also means no lemma is taught by the mexicanism rule.",
    )
    glossing.add_argument(
        "--gloss-offline",
        action="store_true",
        help="use Wiktionary and the cache only, never a model",
    )
    glossing.add_argument(
        "--gloss-provider",
        choices=PROVIDER_NAMES,
        default=CLAUDE,
        help="which model writes the glosses Wiktionary could not: the Claude "
        f"Batches API, or a model running locally under Ollama (default: {CLAUDE})",
    )
    glossing.add_argument(
        "--gloss-model",
        help="override the provider's model, e.g. claude-haiku-4-5 or qwen3:8b",
    )
    glossing.add_argument(
        "--gloss-limit",
        type=int,
        help="send at most this many lemmas to the model, most-used first",
    )
    glossing.add_argument(
        "--cache-dir",
        type=Path,
        default=CACHE_DIR,
        help="where the gloss cache and the kaikki extracts live. Defaults to "
        "molcajete-prep's shared location, which Rocola reads too — point it "
        "somewhere empty for a cold build rather than deleting the shared one.",
    )
    glossing.add_argument(
        "--regloss",
        action="store_true",
        help="ignore cached glosses and fetch them again. Use when a cached "
        "gloss was disambiguated against a different book's sentence.",
    )
    glossing.add_argument(
        "--de-wiktionary",
        choices=(VERBATIM, CONTEXT_ONLY),
        default=CONTEXT_ONLY,
        help="whether a short German Wiktionary gloss is used as it stands, or "
        "demoted to context so the model writes every German gloss "
        f"(default: {CONTEXT_ONLY} — German Wiktionary glosses `lunes` as "
        '"der erste Wochentag", which fits a card and reads like a riddle)',
    )

    local = parser.add_argument_group(
        "local model",
        "Only meaningful with --gloss-provider ollama. A local model saturates "
        "the machine and follows instructions less reliably than a hosted one, "
        "so both defaults are conservative.",
    )
    local.add_argument(
        "--gloss-concurrency",
        type=int,
        default=ProviderOptions.concurrency,
        help="how many requests to have in flight at once (default: "
        f"{ProviderOptions.concurrency})",
    )
    local.add_argument(
        "--gloss-retries",
        type=int,
        default=ProviderOptions.retries,
        help="how many times to re-ask with a stricter prompt after a malformed "
        f"or over-long answer (default: {ProviderOptions.retries})",
    )
    local.add_argument(
        "--gloss-chunk",
        type=int,
        help="lemmas per request. Defaults to 25 for Claude, where a cached "
        "prompt prefix is worth amortizing, and 1 locally, where it is not.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    options = ClassificationOptions(
        min_book_count=args.min_book_count,
        zipf_threshold=args.zipf_threshold,
        max_cards_per_session=args.max_cards,
    )

    gloss_options = GlossingOptions(
        cache_dir=args.cache_dir,
        use_model=not args.gloss_offline,
        regloss=args.regloss,
        model_limit=args.gloss_limit,
        de_wiktionary=args.de_wiktionary,
        provider_options=ProviderOptions(
            name=args.gloss_provider,
            model=args.gloss_model,
            chunk_size=args.gloss_chunk,
            concurrency=args.gloss_concurrency,
            retries=args.gloss_retries,
        ),
    )

    result = build_bundle(
        args.epub,
        book_id=args.book_id,
        title=args.title,
        author=args.author,
        known_lemmas=load_known_lemmas(args.known),
        options=options,
        split_on_heading=args.split_on_heading,
        keep_boilerplate=args.keep_boilerplate,
        include_documents=args.include_documents,
        exclude_documents=args.exclude_documents,
        gloss=not args.no_gloss,
        gloss_options=gloss_options,
        on_status=print_batch_status,
    )

    if args.report_only:
        print(render_report(result, built_at=datetime.now()), end="")
        return 0

    out = Path(args.out)
    bundle_path = write_bundle(
        result.bundle, out / f"{result.book_id}{BUNDLE_SUFFIX}", pretty=args.pretty
    )
    report = render_report(
        result,
        built_at=datetime.now(),
        bundle_bytes=bundle_path.stat().st_size,
    )
    report_path = out / f"{result.book_id}{REPORT_SUFFIX}"
    report_path.write_text(report, encoding="utf-8")

    print(report, end="")
    print(f"\nWrote {bundle_path}")
    print(f"Wrote {report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
