"""Command line entry point for the Anki seed."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from molcajete_prep.seed import FieldScore, dumps, merge, seed_from_text


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="seed_known.py",
        description="Turn an Anki plain-text export into a known.json of lemma strings.",
    )
    parser.add_argument("export", help="path to an Anki 'Notes in Plain Text' .txt")
    parser.add_argument(
        "--out",
        default="known.json",
        help="where to write the lemma list (default: known.json)",
    )
    parser.add_argument(
        "--field",
        type=int,
        help="which column holds the Spanish, 0-indexed. Guessed by default; "
        "the guess and a sample are always printed so a wrong one is obvious.",
    )
    parser.add_argument(
        "--merge",
        action="store_true",
        help="union with whatever is already at --out, rather than replacing it. "
        "SPEC §8 wants this re-runnable as the deck grows.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report what it found and write nothing",
    )
    return parser


def _describe(scores: list[FieldScore], chosen: int, guessed: bool) -> list[str]:
    lines = ["Columns, by how Spanish they look:"]
    for score in scores:
        mark = " <- chosen" + ("" if guessed else " (--field)") if score.index == chosen else ""
        sample = " · ".join(s[:28] for s in score.sample) or "(empty)"
        lines.append(
            f"  [{score.index}] {score.ratio:5.0%} of {score.sampled:>5,} words"
            f"   {sample}{mark}"
        )
    return lines


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    text = Path(args.export).read_text(encoding="utf-8", errors="replace")
    lemmas, chosen, scores = seed_from_text(text, field=args.field)

    print("\n".join(_describe(scores, chosen, guessed=args.field is None)))
    print()

    out = Path(args.out)
    if args.merge and out.exists():
        existing = json.loads(out.read_text(encoding="utf-8"))
        before = len(existing)
        final = merge(existing, lemmas)
        print(f"Merged {len(lemmas):,} lemmas into {before:,} — now {len(final):,}.")
    else:
        final = sorted(lemmas)
        print(f"Found {len(final):,} distinct lemmas.")

    print("Sample: " + ", ".join(final[:12]))

    if args.dry_run:
        print("\n--dry-run, nothing written.")
        return 0

    out.write_text(dumps(final), encoding="utf-8")
    print(f"\nWrote {out}")
    print(f"Use it with: build_bundle.py … --known {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
