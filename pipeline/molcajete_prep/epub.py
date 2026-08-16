"""EPUB to chapters and paragraphs.

The only module that knows what an EPUB is. Everything downstream sees a list of
`ChapterSource`, which is plain text and nothing else.

DRM-free input only. There is no circumvention here and there never will be.
"""

from __future__ import annotations

import posixpath
import re
import unicodedata
from dataclasses import dataclass

import ebooklib
from bs4 import BeautifulSoup
from ebooklib import epub

# Elements whose text is never prose.
_NON_PROSE_TAGS = ("script", "style", "head", "title")

_HEADING_TAGS = ("h1", "h2", "h3", "h4", "h5", "h6")

# Unicode whitespace that should collapse to a plain space before tokenization,
# so that a token's surface form never contains an exotic space the reader would
# have to render specially.
_WHITESPACE_RE = re.compile(r"\s+")

# Soft hyphens are typesetting hints, not characters of the word. Left in place
# they corrupt both the lemma and the surface form.
_SOFT_HYPHEN = "­"


@dataclass(frozen=True)
class ChapterSource:
    """One chapter's worth of prose, extracted and normalized.

    `paragraphs` are already whitespace-normalized: this is the exact text the
    tokenizer receives and the exact text the emitted token surfaces must
    reconstruct.
    """

    title: str
    paragraphs: tuple[str, ...]

    @property
    def is_empty(self) -> bool:
        return not self.paragraphs


def normalize_text(raw: str) -> str:
    """Collapse whitespace and strip typesetting artefacts.

    NFC normalization matters for Spanish: the same accented character can
    arrive either precomposed or as a base plus combining accent, and the two
    forms would otherwise produce two different lemmas.
    """
    text = unicodedata.normalize("NFC", raw)
    text = text.replace(_SOFT_HYPHEN, "")
    return _WHITESPACE_RE.sub(" ", text).strip()


def paragraphs_from_html(html: str) -> list[str]:
    """Extract prose paragraphs from one XHTML document.

    Prefers `<p>` elements. Editions that lay out prose in `<div>`s instead fall
    back to block-level text split on blank lines.
    """
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(_NON_PROSE_TAGS):
        tag.decompose()

    paragraphs = [normalize_text(p.get_text()) for p in soup.find_all("p")]
    if not any(paragraphs):
        body = soup.body or soup
        blocks = body.get_text("\n").split("\n")
        paragraphs = [normalize_text(b) for b in blocks]

    return [p for p in paragraphs if p]


def title_from_html(html: str) -> str | None:
    """First heading in the document, if any."""
    soup = BeautifulSoup(html, "html.parser")
    heading = soup.find(_HEADING_TAGS)
    if heading is None:
        return None
    return normalize_text(heading.get_text()) or None


def split_html_on_headings(html: str) -> list[tuple[str | None, str]]:
    """Split one document into `(title, html)` sections at heading boundaries.

    For editions that pack several chapters into a single spine document. Text
    before the first heading becomes an untitled leading section; if there are no
    headings at all the document is returned whole.
    """
    soup = BeautifulSoup(html, "html.parser")
    root = soup.body or soup

    sections: list[tuple[str | None, list[str]]] = [(None, [])]
    for element in root.find_all(recursive=False):
        if element.name in _HEADING_TAGS:
            sections.append((normalize_text(element.get_text()) or None, []))
        else:
            sections[-1][1].append(str(element))

    populated = [(title, "".join(parts)) for title, parts in sections if "".join(parts).strip()]
    return populated or [(None, html)]


def _toc_titles(book: epub.EpubBook) -> dict[str, str]:
    """Map document filename to its table-of-contents title.

    The TOC is a tree of `Link` and `(Section, children)` nodes; fragments are
    dropped so that several TOC entries pointing into one document all resolve to
    that document.
    """
    titles: dict[str, str] = {}

    def walk(nodes) -> None:
        for node in nodes:
            if isinstance(node, tuple):
                section, children = node[0], node[1]
                if isinstance(section, epub.Link):
                    _record(section)
                walk(children)
            elif isinstance(node, epub.Link):
                _record(node)

    def _record(link: epub.Link) -> None:
        href = link.href.split("#", 1)[0]
        name = posixpath.basename(href)
        title = normalize_text(link.title or "")
        # First entry wins: a document's own TOC title beats a sub-heading that
        # happens to point into the middle of it.
        if name and title and name not in titles:
            titles[name] = title

    walk(book.toc)
    return titles


def _spine_documents(book: epub.EpubBook) -> list[epub.EpubItem]:
    """Content documents in reading order, minus navigation and cover pages."""
    documents = []
    for idref, _linear in book.spine:
        item = book.get_item_with_id(idref)
        if item is None or item.get_type() != ebooklib.ITEM_DOCUMENT:
            continue
        if isinstance(item, (epub.EpubNav, epub.EpubCoverHtml)):
            continue
        documents.append(item)
    return documents


def extract_chapters(
    epub_path: str,
    *,
    split_on_heading: bool = False,
) -> list[ChapterSource]:
    """Read an EPUB into ordered chapters.

    Documents that yield no prose (covers, blank pages, pure navigation) are
    dropped rather than emitted as empty chapters.
    """
    book = epub.read_epub(epub_path)
    toc_titles = _toc_titles(book)

    chapters: list[ChapterSource] = []
    for item in _spine_documents(book):
        html = item.get_content().decode("utf-8", errors="replace")
        filename = posixpath.basename(item.get_name())
        document_title = toc_titles.get(filename)

        if split_on_heading:
            sections = split_html_on_headings(html)
        else:
            sections = [(document_title or title_from_html(html), html)]

        for section_title, section_html in sections:
            paragraphs = paragraphs_from_html(section_html)
            if not paragraphs:
                continue
            title = section_title or document_title or f"Capítulo {len(chapters) + 1}"
            chapters.append(ChapterSource(title=title, paragraphs=tuple(paragraphs)))

    return chapters


def book_metadata(epub_path: str) -> dict[str, str]:
    """Title and author from the EPUB's Dublin Core metadata, where present."""
    book = epub.read_epub(epub_path)

    def first(namespace: str, name: str) -> str:
        values = book.get_metadata(namespace, name)
        return normalize_text(values[0][0]) if values else ""

    return {
        "title": first("DC", "title"),
        "author": first("DC", "creator"),
        "language": first("DC", "language"),
    }
