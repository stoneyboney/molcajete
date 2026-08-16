from __future__ import annotations

from molcajete_prep.epub import (
    ChapterSource,
    book_metadata,
    extract_chapters,
    normalize_text,
    paragraphs_from_html,
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


class TestSplitOnHeadings:
    def test_splits_a_packed_document_into_sections(self):
        html = (
            "<body><h1>Primera parte</h1><p>Uno.</p>"
            "<h1>Segunda parte</h1><p>Dos.</p></body>"
        )

        sections = split_html_on_headings(html)

        assert [title for title, _ in sections] == ["Primera parte", "Segunda parte"]

    def test_returns_the_document_whole_when_it_has_no_headings(self):
        html = "<body><p>Uno.</p></body>"

        assert len(split_html_on_headings(html)) == 1

    def test_title_from_html_reads_the_first_heading(self):
        assert title_from_html("<body><h3>Capítulo 4</h3><p>x</p></body>") == "Capítulo 4"
        assert title_from_html("<body><p>x</p></body>") is None


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
