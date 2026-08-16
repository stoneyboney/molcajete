"""Builds the synthetic fixture EPUB the test suite runs against.

Written rather than downloaded so that no book text is committed to this repo
and so that the expected counts are exact. The prose is deliberately shaped to
exercise every row of the SPEC §5 classification table:

* `sierra`, `fusil`, `caballo`, `jacal` appear in all three chapters
  -> bookCount >= 3, teach
* `soldado` appears twice but is common Spanish
  -> zipf >= 3.5, teach
* `huizache`, `chaparral` appear once and are rare
  -> gloss only
* `Demetrio`, `Macías`, `Anastasio`, `Montañés`
  -> PROPN, skipped entirely

Run directly to regenerate the committed copy:

    uv run python tests/fixtures/fixture_book.py
"""

from __future__ import annotations

from pathlib import Path

from ebooklib import epub

FIXTURE_PATH = Path(__file__).parent / "fixture.epub"

BOOK_TITLE = "Los del cerro"
BOOK_AUTHOR = "Anónimo"

CHAPTERS: list[tuple[str, list[str]]] = [
    (
        "Capítulo 1",
        [
            "Demetrio Macías miró la sierra desde la puerta de su jacal.",
            "Los soldados federales venían por el camino, despacio, "
            "levantando polvo entre los huizaches.",
            "Agarró su fusil, montó el caballo y no volvió la cabeza.",
        ],
    ),
    (
        "Capítulo 2",
        [
            "El caballo subió la sierra con paso corto; Demetrio conocía "
            "cada piedra de aquel camino.",
            "Anastasio Montañés lo alcanzó más arriba, con otro fusil "
            "al hombro y una sonrisa de gusto.",
            "Los soldados quedaron abajo, perdidos en el chaparral, "
            "lejos ya del jacal.",
        ],
    ),
    (
        "Capítulo 3",
        [
            "La sierra guardó a los hombres muchos días.",
            "Comían tortillas duras, bebían agua del arroyo y hablaban poco.",
            "Demetrio limpiaba su fusil todas las noches mientras el "
            "caballo pastaba cerca del jacal abandonado.",
        ],
    ),
]


def _chapter_html(title: str, paragraphs: list[str]) -> bytes:
    """A body fragment, which is what EpubHtml expects.

    ebooklib wraps this in its own XHTML skeleton. Handing it a complete
    document instead makes lxml reject the encoding declaration, and
    `EpubHtml.get_content` swallows that exception and writes an empty file.
    """
    body = "\n".join(f"<p>{p}</p>" for p in paragraphs)
    return f"<h2>{title}</h2>\n{body}".encode()


def build_fixture_epub(path: str | Path) -> Path:
    """Write the fixture EPUB to `path` and return it."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    book = epub.EpubBook()
    book.set_identifier("molcajete-fixture-los-del-cerro")
    book.set_title(BOOK_TITLE)
    book.set_language("es")
    book.add_author(BOOK_AUTHOR)

    items = []
    for index, (title, paragraphs) in enumerate(CHAPTERS, start=1):
        item = epub.EpubHtml(
            title=title,
            file_name=f"chap_{index:02d}.xhtml",
            lang="es",
            uid=f"chap{index:02d}",
        )
        item.content = _chapter_html(title, paragraphs)
        book.add_item(item)
        items.append(item)

    book.toc = tuple(
        epub.Link(item.file_name, item.title, item.id) for item in items
    )
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav", *items]

    # epub3_pages generates a page-list from every document, which chokes on the
    # nav item whose body is still empty at write time. We don't need page maps.
    epub.write_epub(str(path), book, {"epub3_pages": False})
    return path


if __name__ == "__main__":
    print(build_fixture_epub(FIXTURE_PATH))
