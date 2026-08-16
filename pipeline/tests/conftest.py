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
