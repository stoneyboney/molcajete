from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "fixtures"))

from fixture_book import CHAPTERS, build_fixture_epub  # noqa: E402
from fixture_critical_edition import build_critical_edition_epub  # noqa: E402
from fixture_ocr_edition import build_ocr_edition_epub  # noqa: E402

# `nlp`, `no_real_extracts` and `no_shared_cache` are not here. They come from
# molcajete-prep's pytest plugin, because a suite that builds bundles needs
# exactly the same guards this package's own suite does and two copies of a
# guard is one copy too many. See `molcajete_prep/pytest_plugin.py`.


@pytest.fixture(scope="session")
def fixture_epub(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A freshly built synthetic EPUB, so tests never depend on a committed binary."""
    return build_fixture_epub(tmp_path_factory.mktemp("epub") / "fixture.epub")


@pytest.fixture(scope="session")
def critical_edition_epub(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A scholarly edition: apparatus in the spine, packed parts, footnotes."""
    return build_critical_edition_epub(
        tmp_path_factory.mktemp("epub") / "critical-edition.epub"
    )


@pytest.fixture(scope="session")
def ocr_edition_epub(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A scanned edition whose pages are typed `text/html`, not `application/xhtml+xml`."""
    return build_ocr_edition_epub(tmp_path_factory.mktemp("epub") / "ocr-edition.epub")


@pytest.fixture(scope="session")
def fixture_chapters() -> list[tuple[str, list[str]]]:
    """The prose that went into the fixture, for round-trip assertions."""
    return CHAPTERS
