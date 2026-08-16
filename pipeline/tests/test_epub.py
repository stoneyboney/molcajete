from __future__ import annotations

from molcajete_prep.epub import (
    ChapterSource,
    book_metadata,
    extract_chapters,
    normalize_text,
    paragraphs_from_html,
    split_html_on_headings,
    title_from_html,
)


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
