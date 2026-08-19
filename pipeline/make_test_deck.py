#!/usr/bin/env python3
"""Write a synthetic Anki export of the commonest Spanish words.

    uv run python make_test_deck.py --out test-deck.anki.txt

For exercising `seed_known.py` and the app's import without touching a real
deck. Written rather than downloaded, for the same reason as the fixture EPUB:
the expected counts are then exact and nothing personal is in the repo.

Shaped like a real export, because that is the point — tab-separated, `#`
headers, **German in the first column and Spanish in the second**, so the
column detection has to earn its answer rather than defaulting to column 0.

## What a seed is worth

Measured against `Los de abajo`, whose first chapter unseeded wants 263 cards
across 15 sessions:

    --count  200    chapter 1: 211 cards, 12 sessions, book coverage 61.3%
    --count 1000    see the README; the open-class words start coming out

At 200, coverage leaps and the teach set barely moves. That is not a bug — it
is the closed-class rule showing through. The commonest Spanish words are
function words, which the teach set never contained, so seeding them removes
few cards; but they are a large share of the *tokens* on the page, so marking
them known moves coverage enormously. Going further reaches the open-class
vocabulary where the cards actually are.

## The words

`data/test-deck-es-de.tsv`, committed. The Spanish is `wordfreq`'s frequency
order reduced to dictionary forms — a real deck has one note per word, not one
per inflection, so `está`, `fue` and `tiene` are `estar`, `ser` and `tener`
here, and nouns carry their article.

The German is mixed and the file says which is which. The first 244 were
written or corrected by hand; the rest came from the pipeline's own gloss
cache. That tail is unreviewed and it shows — the cache earned its glosses
against a novel's sentences, which is a different job from fitting a card, and
it glosses `es` as "der Rivale". It is there so the column detection has
something to discriminate against; `seed_known.py` reads only the Spanish.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

DATA = Path(__file__).parent / "data" / "test-deck-es-de.tsv"


def load_deck() -> list[tuple[str, str]]:
    """The word list, from `data/test-deck-es-de.tsv`.

    Committed rather than generated on demand: it takes a spaCy load and a
    frequency walk to build, and the whole point of a fixture is that the counts
    are the same for everyone.

    The file's third column says where each German gloss came from. The first
    244 were written or corrected by hand; the rest are the pipeline's own gloss
    cache, unreviewed. That tail is good enough to look at and not good enough
    to study from — it is there so the column detection has something to
    discriminate against, and `seed_known.py` reads only the Spanish.
    """
    if not DATA.exists():
        raise SystemExit(f"{DATA} is missing — it is committed, so this is a bad checkout")

    deck = []
    for line in DATA.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        spanish, german, _source = line.split("\t")
        deck.append((spanish, german))
    return deck


HEADERS = ["#separator:tab", "#html:true", "#notetype:Basic", "#deck:Spanisch::Grundwortschatz"]


def export_text(count: int, deck: list[tuple[str, str]] | None = None) -> str:
    deck = deck if deck is not None else load_deck()
    if count > len(deck):
        raise SystemExit(
            f"--count {count} but the list holds {len(deck)} words. "
            f"Extend {DATA.name}, or ask for fewer."
        )
    lines = list(HEADERS)
    for spanish, german in deck[:count]:
        # German first, deliberately: a reader that assumes column 0 is the
        # target language should fail this file loudly.
        lines.append(f"{german}\t{spanish}\tGrundwortschatz")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="make_test_deck.py",
        description="Write a synthetic Anki export of common Spanish words.",
    )
    parser.add_argument("--out", default="test-deck.anki.txt", help="where to write it")
    parser.add_argument(
        "--count",
        type=int,
        default=200,
        help="how many words, most common first (default: 200, max 1000)",
    )
    args = parser.parse_args(argv)

    out = Path(args.out)
    out.write_text(export_text(args.count), encoding="utf-8")
    print(f"Wrote {out} — {args.count} notes, German in column 0, Spanish in column 1.")
    print(f"Next: uv run python seed_known.py {out} --out known.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
