#!/usr/bin/env python3
"""Write a synthetic Anki export of the commonest Spanish words.

    uv run python make_test_deck.py --out test-deck.anki.txt

For exercising `seed_known.py` and the app's import without touching a real
deck. Written rather than downloaded, for the same reason as the fixture EPUB:
the expected counts are then exact and nothing personal is in the repo.

Shaped like a real export, because that is the point — tab-separated, `#`
headers, **German in the first column and Spanish in the second**, so the
column detection has to earn its answer rather than defaulting to column 0.

## What a 200-word seed actually does

Measured against `Los de abajo`:

    nothing seeded    chapter 1: 263 cards, 15 sessions, book coverage  4.3%
    top-200 seed      chapter 1: 235 cards, 14 sessions, book coverage 58.9%

Coverage leaps and the teach set barely moves, which is not a bug — it is the
closed-class rule showing through. The commonest 200 Spanish words are almost
all function words, which the teach set never contained, so seeding them removes
few cards. They are a large share of the *tokens* on the page, though, so
marking them known moves coverage enormously.

If you want the teach set to move, seed more: `--count 1000` reaches the open-
class vocabulary where the cards actually are.

## The words

The Spanish is `wordfreq`'s frequency order, reduced to dictionary forms — a
real deck has one note per word, not one per inflection, so `está`, `fue` and
`tiene` are `estar`, `ser` and `tener` here. Nouns carry their article, as they
would on a card you were actually studying.

The German is written out rather than looked up. The gloss cache has 127 of
these, but it also has `es` glossed as "der Rivale" — fine as a lexicon entry
for a book that used the word that way, wrong on a vocabulary card.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# (Spanish, German). Frequency order, dictionary forms.
DECK: list[tuple[str, str]] = [
    ("de", "von, aus"), ("el", "der"), ("que", "dass, der"), ("en", "in, an"),
    ("y", "und"), ("a", "zu, nach"), ("no", "nein, nicht"), ("uno", "ein, eins"),
    ("él", "er"), ("por", "für, durch"), ("ser", "sein"), ("con", "mit"),
    ("para", "für, um zu"), ("su", "sein, ihr"), ("como", "wie, als"),
    ("yo", "ich"), ("más", "mehr"), ("si", "wenn, ob"), ("pero", "aber"),
    ("tú", "du"), ("o", "oder"), ("mi", "mein"), ("este", "dieser"),
    ("todo", "alles, ganz"), ("ya", "schon, bereits"), ("haber", "haben"),
    ("cuando", "wenn, als"), ("sin", "ohne"), ("estar", "sein, sich befinden"),
    ("mucho", "viel, sehr"), ("sobre", "über, auf"), ("también", "auch"),
    ("ese", "jener"), ("tener", "haben"), ("porque", "weil"),
    ("qué", "was, welcher"), ("así", "so"), ("el año", "das Jahr"),
    ("dos", "zwei"), ("bien", "gut"), ("entre", "zwischen"),
    ("poder", "können, die Macht"), ("desde", "seit, von"), ("hasta", "bis"),
    ("hacer", "machen, tun"), ("ahora", "jetzt"), ("la vez", "das Mal"),
    ("nada", "nichts"), ("ni", "weder, noch"), ("dónde", "wo"),
    ("la parte", "der Teil"), ("solo", "allein, nur"), ("algo", "etwas"),
    ("el tiempo", "die Zeit, das Wetter"), ("el día", "der Tag"),
    ("mejor", "besser"), ("tanto", "so viel"), ("ver", "sehen"),
    ("la vida", "das Leben"), ("mismo", "gleich, selbst"),
    ("siempre", "immer"), ("cada", "jeder"), ("después", "danach"),
    ("la gente", "die Leute"), ("el mundo", "die Welt"), ("ir", "gehen, fahren"),
    ("otro", "anderer"), ("las gracias", "der Dank"), ("la cosa", "die Sache"),
    ("gran", "groß"), ("menos", "weniger"), ("nunca", "nie"),
    ("la persona", "die Person"), ("antes", "vorher"), ("poco", "wenig"),
    ("el trabajo", "die Arbeit"), ("durante", "während"),
    ("el lugar", "der Ort"), ("creer", "glauben"), ("cómo", "wie"),
    ("el hecho", "die Tatsache"), ("querer", "wollen, mögen"),
    ("aunque", "obwohl"), ("contra", "gegen"), ("contar", "zählen, erzählen"),
    ("decir", "sagen"), ("el gobierno", "die Regierung"), ("el país", "das Land"),
    ("la casa", "das Haus"), ("la forma", "die Form, die Art"),
    ("nuevo", "neu"), ("aquí", "hier"), ("sí", "ja"), ("hoy", "heute"),
    ("alguien", "jemand"), ("quien", "wer"), ("tres", "drei"),
    ("el caso", "der Fall"), ("el momento", "der Augenblick"),
    ("bueno", "gut"), ("la ciudad", "die Stadt"), ("nuestro", "unser"),
    ("luego", "dann, später"), ("nacional", "national"),
    ("parecer", "scheinen"), ("pues", "also, denn"), ("la verdad", "die Wahrheit"),
    ("la historia", "die Geschichte"), ("mientras", "während"),
    ("nadie", "niemand"), ("primero", "erster"), ("cual", "welcher"),
    ("deber", "müssen, sollen"), ("entonces", "dann, damals"),
    ("el tipo", "die Art, der Typ"), ("alguno", "irgendein"),
    ("general", "allgemein"), ("mayor", "größer, älter"), ("tal", "solcher"),
    ("además", "außerdem"), ("mal", "schlecht"), ("según", "laut, gemäß"),
    ("el acuerdo", "die Vereinbarung"), ("cualquiera", "irgendeiner"),
    ("dar", "geben"), ("la manera", "die Art und Weise"),
    ("el nombre", "der Name"), ("la ley", "das Gesetz"),
    ("el medio", "die Mitte, das Mittel"), ("el partido", "die Partei, das Spiel"),
    ("bajo", "unter, niedrig"), ("hacia", "in Richtung"), ("sino", "sondern"),
    ("el grupo", "die Gruppe"), ("el hombre", "der Mann"), ("buen", "gut"),
    ("la mujer", "die Frau"), ("el sistema", "das System"), ("casi", "fast"),
    ("el fin", "das Ende"), ("la noche", "die Nacht"),
    ("el pasado", "die Vergangenheit"), ("el presidente", "der Präsident"),
    ("ahí", "da, dort"), ("dentro", "innerhalb"), ("la familia", "die Familie"),
    ("el lado", "die Seite"), ("aún", "noch"), ("el pueblo", "das Dorf, das Volk"),
    ("final", "endgültig, das Ende"), ("político", "politisch"),
    ("el problema", "das Problem"), ("el punto", "der Punkt"),
    ("el agua", "das Wasser"), ("el equipo", "die Mannschaft, die Ausrüstung"),
    ("la guerra", "der Krieg"), ("saber", "wissen, können"), ("ante", "vor"),
    ("sin embargo", "jedoch, dennoch"), ("el favor", "der Gefallen"),
    ("gustar", "gefallen"), ("importante", "wichtig"),
    ("la información", "die Information"), ("la mañana", "der Morgen"),
    ("pasar", "vorbeigehen, geschehen"), ("la semana", "die Woche"),
    ("claro", "klar"), ("el dinero", "das Geld"), ("social", "sozial"),
    ("el ejemplo", "das Beispiel"), ("el estado", "der Staat, der Zustand"),
    ("la hora", "die Stunde"), ("igual", "gleich"), ("el millón", "die Million"),
    ("el número", "die Zahl"), ("hablar", "sprechen"), ("el señor", "der Herr"),
    ("el centro", "das Zentrum"), ("el derecho", "das Recht"),
    ("faltar", "fehlen"), ("grande", "groß"), ("el amigo", "der Freund"),
    ("el cambio", "die Veränderung"), ("la idea", "die Idee"),
    ("la muerte", "der Tod"), ("la tarde", "der Nachmittag"),
    ("tras", "nach, hinter"), ("a través", "durch, hindurch"),
    ("el mes", "der Monat"), ("el niño", "das Kind"), ("la mano", "die Hand"),
    ("el ojo", "das Auge"), ("la puerta", "die Tür"), ("el padre", "der Vater"),
    ("la madre", "die Mutter"), ("el libro", "das Buch"),
    ("venir", "kommen"),
    ("salir", "hinausgehen"), ("llegar", "ankommen"), ("llevar", "tragen"),
    ("dejar", "lassen"), ("seguir", "folgen, weitermachen"),
    ("encontrar", "finden"), ("llamar", "rufen, nennen"), ("pensar", "denken"),
    ("volver", "zurückkehren"), ("tomar", "nehmen"), ("conocer", "kennen"),
    ("vivir", "leben"), ("sentir", "fühlen"), ("mirar", "schauen"),
    ("escribir", "schreiben"), ("leer", "lesen"), ("abrir", "öffnen"),
    ("cerrar", "schließen"), ("empezar", "anfangen"), ("trabajar", "arbeiten"),
]

HEADERS = ["#separator:tab", "#html:true", "#notetype:Basic", "#deck:Spanisch::Grundwortschatz"]


def export_text(count: int) -> str:
    if count > len(DECK):
        raise SystemExit(
            f"--count {count} but the deck holds {len(DECK)} words. "
            "Add more to DECK, or ask for fewer."
        )
    lines = list(HEADERS)
    for spanish, german in DECK[:count]:
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
        "--count", type=int, default=200, help="how many words (default: 200)"
    )
    args = parser.parse_args(argv)

    out = Path(args.out)
    out.write_text(export_text(args.count), encoding="utf-8")
    print(f"Wrote {out} — {args.count} notes, German in column 0, Spanish in column 1.")
    print(f"Next: uv run python seed_known.py {out} --out known.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
