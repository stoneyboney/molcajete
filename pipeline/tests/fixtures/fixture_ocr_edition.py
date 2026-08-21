"""Builds a synthetic EPUB whose content documents are typed `text/html`.

Real-world trigger: `El principito`, an Internet Archive `hocr-to-epub` scan.
EPUB3 content documents are supposed to be `application/xhtml+xml`; ebooklib
only classifies an item as `ITEM_DOCUMENT` when the media type is exactly
that string, so a `text/html`-typed page comes back as `ITEM_UNKNOWN` and
`_spine_documents` used to drop it — silently, along with every other page
sharing that media type. A book built this way yielded zero chapters and no
clue why.

`ebooklib.epub.EpubHtml` always writes `application/xhtml+xml`, so this
fixture bypasses it and adds a plain `EpubItem` with the media type set by
hand — the only way to reproduce the bug at all.
"""

from __future__ import annotations

from pathlib import Path

from ebooklib import epub

FIXTURE_PATH = Path(__file__).parent / "ocr-edition.epub"

TITLE = "Edición escaneada"
AUTHOR = "Archivo"

# One conformant chapter and one typed like the real-world trigger, so a
# regression that reintroduces the bug fails on the second and only the
# second.
CHAPTERS: list[tuple[str, str, str]] = [
    ("application/xhtml+xml", "Capítulo 1", "El caballo subió la sierra."),
    ("text/html", "Capítulo 2", "Los soldados quedaron abajo, perdidos."),
]


def build_ocr_edition_epub(path: str | Path) -> Path:
    """Write the fixture EPUB to `path` and return it."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    book = epub.EpubBook()
    book.set_identifier("molcajete-fixture-ocr-edition")
    book.set_title(TITLE)
    book.set_language("es")
    book.add_author(AUTHOR)

    items = []
    for index, (media_type, title, prose) in enumerate(CHAPTERS, start=1):
        item = epub.EpubItem(
            uid=f"chapter_{index}",
            file_name=f"page_{index}.html",
            media_type=media_type,
            content=f"<html><body><p>{prose}</p></body></html>".encode(),
        )
        book.add_item(item)
        items.append(item)

    book.toc = tuple(epub.Link(item.file_name, title, item.id) for item, (_, title, _) in zip(items, CHAPTERS, strict=True))
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav", *items]

    epub.write_epub(str(path), book, {"epub3_pages": False})
    return path


if __name__ == "__main__":
    print(build_ocr_edition_epub(FIXTURE_PATH))
