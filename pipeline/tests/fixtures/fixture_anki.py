"""A synthetic Anki plain-text export.

Written rather than committed, for the same reason as the fixture EPUB: no real
deck belongs in this repo. Shaped to exercise what a real export throws at the
seed reader —

* `#`-prefixed header lines, which current Anki versions emit
* a note type whose *second* column is the Spanish, so a reader that assumes
  the first column gets German and seeds nothing useful
* HTML, cloze deletions, `[sound:…]` tags and `&nbsp;` inside fields
* multi-value fields separated by commas and semicolons
* a proper noun, which §5 never teaches and the seed must not record
* inflected forms, so the lemmatization is doing something visible
"""

from __future__ import annotations

from pathlib import Path

FIXTURE_PATH = Path(__file__).parent / "anki-export.txt"

# (German, Spanish, extra) — deliberately not Spanish-first.
NOTES: list[tuple[str, str, str]] = [
    ("der Hund", "el perro", "A1"),
    ("die Katze", "<b>el gato</b>", "A1"),
    ("laufen", "correr", "A1"),
    ("die H&auml;user", "las casas", "A2"),
    ("sprechen", "{{c1::hablar::verbo}}", "A2"),
    ("die Sierra", "la sierra[sound:sierra.mp3]", "B1"),
    ("Mexiko", "México", "B1"),
    ("die Lust, der Wille", "las ganas; el deseo", "B1"),
    ("er sagte", "dijo", "B1"),
    ("nur", "nomás", "B2"),
]

HEADERS = [
    "#separator:tab",
    "#html:true",
    "#notetype column:1",
    "#deck column:2",
]


def export_text() -> str:
    lines = list(HEADERS)
    for german, spanish, extra in NOTES:
        lines.append("\t".join((german, spanish, extra)))
    return "\n".join(lines) + "\n"


def build_anki_export(path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(export_text(), encoding="utf-8")
    return path


if __name__ == "__main__":
    print(build_anki_export(FIXTURE_PATH))
