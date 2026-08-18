"""A synthetic scholarly edition, for the three faults such editions expose.

Modelled on the Marta Portal `Los de abajo`, which is what prompted all of this:

* **The apparatus is as long as the novel and sits in the same spine.** An
  introduction, endnotes and a bibliography, all modern prose that would
  otherwise become chapters of the book and words in its lexicon.
* **The novel is packed** — each part is one document holding several numbered
  chapters, split apart by `--split-on-heading`.
* **Footnote markers are inline**, as `<a href="notas#n1"><sup>[1]</sup></a>`,
  and survive naive text extraction as `federales[1]`.
* **The table of contents addresses chapters by fragment**, so a chapter's real
  name is reachable only through the `id` on its heading. Without that the
  titles collapse to `I`, `II` and repeat across the parts.

Deliberately tiny. The point is the shape, not the prose.
"""

from __future__ import annotations

from pathlib import Path

from ebooklib import epub

FIXTURE_PATH = Path(__file__).parent / "critical-edition.epub"

BOOK_TITLE = "Los del cerro (ed. crítica)"
BOOK_AUTHOR = "Anónimo"

# Chapter titles as the table of contents gives them, keyed by heading id. The
# heading text itself is only the numeral.
TOC_CHAPTER_TITLES = {
    "ch_i": "I. Miró la sierra",
    "ch_ii": "II. El caballo subió",
    "ch_iii": "III. La sierra guardó",
}


def _footnoted(text: str, number: int) -> str:
    """A paragraph carrying a reference marker, exactly as the real book does."""
    return (
        f"<p>{text}"
        f'<a href="../Text/notas.xhtml#nt{number}" id="rf{number}">'
        f"<sup>[{number}]</sup></a>.</p>"
    )


PRIMERA_PARTE = (
    '<h1 title="Primera parte">Primera parte</h1>\n'
    '<h2 id="ch_i">I</h2>\n'
    + _footnoted("Demetrio Macías miró la sierra desde su jacal", 1)
    + "<p>Los soldados federales venían por el camino.</p>\n"
    '<h2 id="ch_ii">II</h2>\n'
    + _footnoted("El caballo subió la sierra con paso corto", 2)
)

SEGUNDA_PARTE = (
    '<h1 title="Segunda parte">Segunda parte</h1>\n'
    '<h2 id="ch_iii">III</h2>\n'
    "<p>La sierra guardó a los hombres muchos días.</p>"
)

# The apparatus. Its vocabulary — 'bibliografía', 'crítica', 'edición' — is
# exactly what must not reach the lexicon.
INTRODUCCION = (
    "<h1>Introducción</h1>\n"
    "<p>Esta edición crítica reúne los estudios más recientes.</p>"
)
BIBLIOGRAFIA = (
    "<h1>Bibliografía</h1>\n"
    "<p>Obras y reseñas críticas sobre la novela mexicana contemporánea.</p>"
)
NOTAS = (
    "<h1>Notas</h1>\n"
    '<p id="nt1">Federales: soldados del gobierno.</p>\n'
    '<p id="nt2">Jacal: choza rural mexicana.</p>'
)

DOCUMENTS: list[tuple[str, str, str]] = [
    # (filename, table-of-contents title, body html)
    ("Introduccion.xhtml", "Introducción", INTRODUCCION),
    ("Bibliografia.xhtml", "Bibliografía", BIBLIOGRAFIA),
    ("PrimeraParte.xhtml", "Primera parte", PRIMERA_PARTE),
    ("SegundaParte.xhtml", "Segunda parte", SEGUNDA_PARTE),
    ("notas.xhtml", "Notas", NOTAS),
]

NOVEL_DOCUMENTS = ("PrimeraParte.xhtml", "SegundaParte.xhtml")

# Which packed chapters live in which document.
CHAPTER_ANCHORS: dict[str, tuple[str, ...]] = {
    "PrimeraParte.xhtml": ("ch_i", "ch_ii"),
    "SegundaParte.xhtml": ("ch_iii",),
}


def build_critical_edition_epub(path: str | Path) -> Path:
    """Write the fixture EPUB to `path` and return it."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    book = epub.EpubBook()
    book.set_identifier("molcajete-fixture-critical-edition")
    book.set_title(BOOK_TITLE)
    book.set_language("es")
    book.add_author(BOOK_AUTHOR)

    items = []
    for index, (filename, title, body) in enumerate(DOCUMENTS, start=1):
        item = epub.EpubHtml(
            title=title, file_name=filename, lang="es", uid=f"doc{index:02d}"
        )
        item.content = body.encode()
        book.add_item(item)
        items.append(item)

    by_name = {item.file_name: item for item in items}

    # Document-level entries, plus fragment entries for the packed chapters —
    # which is how the real edition names chapters that share a file.
    toc: list[epub.Link] = []
    for filename, title, _body in DOCUMENTS:
        toc.append(epub.Link(filename, title, by_name[filename].id))
        for anchor in CHAPTER_ANCHORS.get(filename, ()):
            toc.append(
                epub.Link(f"{filename}#{anchor}", TOC_CHAPTER_TITLES[anchor], anchor)
            )

    book.toc = tuple(toc)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav", *items]

    epub.write_epub(str(path), book, {"epub3_pages": False})
    return path


if __name__ == "__main__":
    print(build_critical_edition_epub(FIXTURE_PATH))
