from __future__ import annotations

import pytest

from molcajete_book.epub import (
    ChapterSource,
    book_metadata,
    extract_chapters,
    normalize_text,
    paragraphs_from_html,
    select_documents,
    split_html_on_headings,
    strip_gutenberg_boilerplate,
    title_from_html,
)


def chapter(*paragraphs: str, title: str = "Capítulo") -> ChapterSource:
    return ChapterSource(title=title, paragraphs=tuple(paragraphs))


def test_extracts_one_chapter_per_spine_document(fixture_epub):
    chapters = extract_chapters(str(fixture_epub))

    assert len(chapters) == 3
    assert [c.title for c in chapters] == ["Capítulo 1", "Capítulo 2", "Capítulo 3"]
    assert all(isinstance(c, ChapterSource) for c in chapters)


def test_navigation_and_toc_documents_are_not_chapters(fixture_epub):
    chapters = extract_chapters(str(fixture_epub))

    # The spine leads with the nav document. If it leaked through we would see a
    # fourth chapter whose paragraphs are a list of chapter titles.
    assert len(chapters) == 3
    assert not any("Capítulo 2" in p for p in chapters[0].paragraphs)


def test_paragraphs_survive_extraction_intact(fixture_epub, fixture_chapters):
    chapters = extract_chapters(str(fixture_epub))

    for chapter, (_title, expected) in zip(chapters, fixture_chapters, strict=True):
        assert list(chapter.paragraphs) == expected


def test_headings_do_not_become_paragraphs(fixture_epub):
    chapters = extract_chapters(str(fixture_epub))

    assert "Capítulo 1" not in chapters[0].paragraphs


def test_metadata_comes_from_dublin_core(fixture_epub):
    meta = book_metadata(str(fixture_epub))

    assert meta["title"] == "Los del cerro"
    assert meta["author"] == "Anónimo"
    assert meta["language"] == "es"


class TestNormalizeText:
    def test_collapses_runs_of_whitespace(self):
        assert normalize_text("el   caballo\n\tsubió  ") == "el caballo subió"

    def test_collapses_non_breaking_space(self):
        assert normalize_text("cien\xa0pesos") == "cien pesos"

    def test_strips_soft_hyphens(self):
        assert normalize_text("ca\xadba\xadllo") == "caballo"

    def test_composes_decomposed_accents(self):
        # Combining tilde plus combining acute. Left decomposed, this and the
        # precomposed spelling would lemmatize to two different entries.
        decomposed = "Montan\u0303e\u0301s"
        assert decomposed != "Monta\u00f1\u00e9s"
        assert normalize_text(decomposed) == "Monta\u00f1\u00e9s"


class TestParagraphsFromHtml:
    def test_prefers_p_elements(self):
        html = "<body><h2>Título</h2><p>Uno.</p><p>Dos.</p></body>"

        assert paragraphs_from_html(html) == ["Uno.", "Dos."]

    def test_drops_empty_paragraphs(self):
        html = "<body><p>Uno.</p><p>  </p><p></p><p>Dos.</p></body>"

        assert paragraphs_from_html(html) == ["Uno.", "Dos."]

    def test_falls_back_to_blocks_when_there_are_no_paragraphs(self):
        html = "<body><div>Uno.</div><div>Dos.</div></body>"

        assert paragraphs_from_html(html) == ["Uno.", "Dos."]

    def test_ignores_scripts_and_styles(self):
        html = "<body><style>p{color:red}</style><p>Uno.</p></body>"

        assert paragraphs_from_html(html) == ["Uno."]

    def test_drops_footnote_markers_and_closes_the_text_up(self):
        # An annotated edition puts the marker inside the sentence. Left in, the
        # reader has to render `federales[54]` and the lexicon has to hold it.
        html = (
            "<body><p>¿Y que fueran siendo federales"
            '<a href="notas.xhtml#nt54" id="rf54"><sup>[54]</sup></a>?</p></body>'
        )

        assert paragraphs_from_html(html) == ["¿Y que fueran siendo federales?"]

    def test_drops_a_marker_that_is_not_wrapped_in_a_link(self):
        html = "<body><p>tortillas<sup>[55]</sup> en taco.</p></body>"

        assert paragraphs_from_html(html) == ["tortillas en taco."]


class TestSplitOnHeadings:
    def test_splits_a_packed_document_into_sections(self):
        html = (
            "<body><h1>Primera parte</h1><p>Uno.</p>"
            "<h1>Segunda parte</h1><p>Dos.</p></body>"
        )

        sections = split_html_on_headings(html)

        assert [s.title for s in sections] == ["Primera parte", "Segunda parte"]

    def test_returns_the_document_whole_when_it_has_no_headings(self):
        html = "<body><p>Uno.</p></body>"

        assert len(split_html_on_headings(html)) == 1

    def test_carries_the_heading_id_so_the_toc_can_be_consulted(self):
        html = '<body><h2 id="ch_i">I</h2><p>Uno.</p></body>'

        [section] = split_html_on_headings(html)

        assert section.title == "I"
        assert section.anchor == "ch_i"

    def test_a_heading_without_an_id_has_no_anchor(self):
        html = "<body><h2>I</h2><p>Uno.</p></body>"

        assert split_html_on_headings(html)[0].anchor is None

    def test_title_from_html_reads_the_first_heading(self):
        assert title_from_html("<body><h3>Capítulo 4</h3><p>x</p></body>") == "Capítulo 4"
        assert title_from_html("<body><p>x</p></body>") is None


class TestSelectDocuments:
    """A critical edition carries as much apparatus as novel, in one spine.

    Left in, the editor's introduction and the bibliography become chapters of
    the book and their words become the book's vocabulary — inflating the
    `bookCount` that decides what gets taught, on prose the reader will never
    see. Gutenberg's licence has markers to find it by; an editor's essay does
    not, so which documents are the book is said at the command line.
    """

    NAMES = [
        "Introduccion.xhtml",
        "Bibliografia.xhtml",
        "PrimeraParte.xhtml",
        "SegundaParte.xhtml",
        "notas.xhtml",
    ]

    def test_no_filters_keeps_everything_in_order(self):
        assert select_documents(self.NAMES) == self.NAMES

    def test_include_narrows_to_the_matches(self):
        assert select_documents(self.NAMES, include=["*Parte*"]) == [
            "PrimeraParte.xhtml",
            "SegundaParte.xhtml",
        ]

    def test_include_takes_several_globs(self):
        selected = select_documents(
            self.NAMES, include=["PrimeraParte*", "SegundaParte*"]
        )

        assert selected == ["PrimeraParte.xhtml", "SegundaParte.xhtml"]

    def test_exclude_removes_the_matches(self):
        selected = select_documents(
            self.NAMES, exclude=["Introduccion*", "Bibliografia*", "notas*"]
        )

        assert selected == ["PrimeraParte.xhtml", "SegundaParte.xhtml"]

    def test_exclude_applies_after_include(self):
        selected = select_documents(
            self.NAMES, include=["*.xhtml"], exclude=["notas*", "Bib*", "Intro*"]
        )

        assert selected == ["PrimeraParte.xhtml", "SegundaParte.xhtml"]

    def test_an_include_that_matches_nothing_raises(self):
        # Silently producing an empty book would surface much later, as a
        # confusing "yielded no chapters with prose in them".
        with pytest.raises(ValueError, match="matched none of"):
            select_documents(self.NAMES, include=["TerceraParte*"])

    def test_an_exclude_that_removes_everything_raises(self):
        with pytest.raises(ValueError, match="removed every document"):
            select_documents(self.NAMES, exclude=["*"])


class TestCriticalEdition:
    def test_the_apparatus_is_a_chapter_unless_it_is_filtered_out(
        self, critical_edition_epub
    ):
        chapters = extract_chapters(str(critical_edition_epub))

        titles = [c.title for c in chapters]
        assert "Introducción" in titles
        assert "Bibliografía" in titles

    def test_including_only_the_novel_drops_the_apparatus(
        self, critical_edition_epub
    ):
        chapters = extract_chapters(
            str(critical_edition_epub),
            include_documents=["PrimeraParte*", "SegundaParte*"],
        )

        titles = [c.title for c in chapters]
        assert "Introducción" not in titles
        assert "Bibliografía" not in titles
        assert "Notas" not in titles

    def test_the_apparatus_vocabulary_does_not_reach_the_prose(
        self, critical_edition_epub
    ):
        chapters = extract_chapters(
            str(critical_edition_epub),
            include_documents=["PrimeraParte*", "SegundaParte*"],
        )

        prose = " ".join(p for c in chapters for p in c.paragraphs)
        for word in ("bibliografía", "crítica", "edición", "reseñas"):
            assert word not in prose.lower()

    def test_no_footnote_marker_survives_into_the_prose(self, critical_edition_epub):
        chapters = extract_chapters(
            str(critical_edition_epub),
            include_documents=["PrimeraParte*", "SegundaParte*"],
        )

        prose = " ".join(p for c in chapters for p in c.paragraphs)
        assert "[1]" not in prose
        assert "[2]" not in prose
        assert "jacal." in prose  # and the sentence still ends properly

    def test_packed_chapters_take_their_names_from_the_toc_fragment(
        self, critical_edition_epub
    ):
        # Both parts number their chapters from the heading text alone, so
        # without the fragment lookup these would be "I", "II", "III" — and in
        # a real book the numbering restarts, so they would also collide.
        chapters = extract_chapters(
            str(critical_edition_epub),
            split_on_heading=True,
            include_documents=["PrimeraParte*", "SegundaParte*"],
        )

        assert [c.title for c in chapters] == [
            "I. Miró la sierra",
            "II. El caballo subió",
            "III. La sierra guardó",
        ]

    def test_titles_are_unique_so_the_chapter_list_is_readable(
        self, critical_edition_epub
    ):
        chapters = extract_chapters(
            str(critical_edition_epub),
            split_on_heading=True,
            include_documents=["PrimeraParte*", "SegundaParte*"],
        )

        titles = [c.title for c in chapters]
        assert len(set(titles)) == len(titles)

    def test_excluding_the_apparatus_reaches_the_same_place(
        self, critical_edition_epub
    ):
        included = extract_chapters(
            str(critical_edition_epub),
            include_documents=["PrimeraParte*", "SegundaParte*"],
        )
        excluded = extract_chapters(
            str(critical_edition_epub),
            exclude_documents=["Introduccion*", "Bibliografia*", "notas*"],
        )

        assert included == excluded


class TestGutenbergBoilerplate:
    """Project Gutenberg's licence is ~2,900 tokens of English legal prose.

    Left in, it becomes a chapter of the book and its words become Spanish
    "vocabulary" — 'accepting', 'paragraph', 'trademark' all turned up in the
    lexicon of the first real build.
    """

    START = "*** START OF THE PROJECT GUTENBERG EBOOK LAS NOCHES ***"
    END = "*** END OF THE PROJECT GUTENBERG EBOOK LAS NOCHES ***"

    def test_text_before_the_start_marker_is_dropped(self):
        chapters = [chapter("Produced by a volunteer.", self.START, "El caballo subió.")]

        stripped = strip_gutenberg_boilerplate(chapters)

        assert stripped == [chapter("El caballo subió.")]

    def test_text_after_the_end_marker_is_dropped(self):
        chapters = [chapter(self.START, "El caballo subió.", self.END, "Section 1.")]

        stripped = strip_gutenberg_boilerplate(chapters)

        assert stripped == [chapter("El caballo subió.")]

    def test_whole_chapters_after_the_end_marker_are_dropped(self):
        chapters = [
            chapter(self.START, "El caballo subió."),
            chapter(self.END, "THE FULL PROJECT GUTENBERG LICENSE"),
            chapter("More licence text."),
        ]

        stripped = strip_gutenberg_boilerplate(chapters)

        assert stripped == [chapter("El caballo subió.")]

    def test_the_markers_themselves_are_not_kept_as_prose(self):
        chapters = [chapter(self.START, "El caballo subió.")]

        stripped = strip_gutenberg_boilerplate(chapters)

        assert all("PROJECT GUTENBERG" not in p for c in stripped for p in c.paragraphs)

    def test_an_end_marker_without_a_start_marker_still_truncates(self):
        chapters = [chapter("El caballo subió.", self.END, "Section 1.")]

        stripped = strip_gutenberg_boilerplate(chapters)

        assert stripped == [chapter("El caballo subió.")]

    def test_a_book_with_no_markers_is_untouched(self):
        chapters = [chapter("El caballo subió."), chapter("La sierra calló.")]

        assert strip_gutenberg_boilerplate(chapters) == chapters

    def test_the_fixture_epub_is_unaffected(self, fixture_epub):
        with_stripping = extract_chapters(str(fixture_epub))
        without = extract_chapters(str(fixture_epub), keep_boilerplate=True)

        assert with_stripping == without


class TestNonConformantMediaType:
    """`El principito`: an Internet Archive `hocr-to-epub` scan whose pages are
    all typed `text/html`. ebooklib only classifies `application/xhtml+xml` as
    a content document, so every page came back `ITEM_UNKNOWN` and the whole
    book disappeared with "yielded no chapters with prose in them" — nothing
    pointed at the media type as the cause.
    """

    def test_a_text_html_page_is_still_extracted(self, ocr_edition_epub):
        chapters = extract_chapters(str(ocr_edition_epub))

        assert len(chapters) == 2
        assert chapters[1].paragraphs == ("Los soldados quedaron abajo, perdidos.",)

    def test_conformant_and_nonconformant_pages_extract_identically(
        self, ocr_edition_epub
    ):
        chapters = extract_chapters(str(ocr_edition_epub))

        # Same shape either way — the media type is a parsing detail, not
        # something that should show up in the extracted prose.
        assert chapters[0].paragraphs == ("El caballo subió la sierra.",)
        assert chapters[1].paragraphs == ("Los soldados quedaron abajo, perdidos.",)
