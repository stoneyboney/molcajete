from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "fixtures"))

from fixture_book import CHAPTERS, build_fixture_epub  # noqa: E402


@pytest.fixture(scope="session")
def fixture_epub(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A freshly built synthetic EPUB, so tests never depend on a committed binary."""
    return build_fixture_epub(tmp_path_factory.mktemp("epub") / "fixture.epub")


@pytest.fixture(scope="session")
def fixture_chapters() -> list[tuple[str, list[str]]]:
    """The prose that went into the fixture, for round-trip assertions."""
    return CHAPTERS


@pytest.fixture(scope="session")
def nlp():
    """The loaded spaCy pipeline. Session-scoped: loading it costs a second."""
    from molcajete_prep.nlp import load_pipeline

    return load_pipeline()


@pytest.fixture(autouse=True)
def no_real_extracts(monkeypatch):
    """Point the glossing pass at a directory that does not exist.

    Without this, any test that builds a bundle without saying `gloss=False`
    streams the 22.9 GB English Wiktionary dump — a minute per test, silently,
    and only on machines that happen to have downloaded it. A path that cannot
    exist turns that into an immediate, explicit SourceUnavailableError.

    Deliberately not under `tmp_path`: several tests assert their `tmp_path` is
    empty, and a stray directory there would fail them for the wrong reason.
    """
    from molcajete_prep.glossing import pipeline

    monkeypatch.setattr(
        pipeline, "DEFAULT_EXTRACT_DIR", Path("/nonexistent/molcajete-extracts")
    )


@pytest.fixture(autouse=True)
def no_shared_cache(monkeypatch, tmp_path):
    """Never let a test read or write the developer's real gloss cache."""
    from molcajete_prep.glossing import cache as cache_module

    monkeypatch.setattr(
        cache_module, "DEFAULT_CACHE_PATH", tmp_path / "test-glosses.sqlite3"
    )
