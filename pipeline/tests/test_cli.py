from __future__ import annotations

import json

import pytest

from molcajete_book.cli import BUNDLE_SUFFIX, REPORT_SUFFIX, load_known_lemmas, main
from molcajete_book.schema import validate_bundle


def test_build_writes_a_bundle_and_a_report(fixture_epub, tmp_path, capsys):
    exit_code = main([str(fixture_epub), "--out", str(tmp_path), "--no-gloss"])
    capsys.readouterr()

    assert exit_code == 0
    bundle_path = tmp_path / f"anonimo-los-del-cerro{BUNDLE_SUFFIX}"
    report_path = tmp_path / f"anonimo-los-del-cerro{REPORT_SUFFIX}"
    assert bundle_path.exists()
    assert report_path.exists()
    validate_bundle(json.loads(bundle_path.read_text(encoding="utf-8")))


def test_book_id_can_be_overridden(fixture_epub, tmp_path, capsys):
    main(
        [str(fixture_epub), "--out", str(tmp_path), "--no-gloss", "--book-id", "azuela-los-de-abajo"]
    )
    capsys.readouterr()

    assert (tmp_path / f"azuela-los-de-abajo{BUNDLE_SUFFIX}").exists()


def test_title_and_author_can_be_overridden(fixture_epub, tmp_path, capsys):
    main(
        [
            str(fixture_epub),
            "--out",
            str(tmp_path),
            "--no-gloss",
            "--title",
            "Los de abajo",
            "--author",
            "Mariano Azuela",
        ]
    )
    capsys.readouterr()

    path = tmp_path / f"azuela-los-de-abajo{BUNDLE_SUFFIX}"
    bundle = json.loads(path.read_text(encoding="utf-8"))
    assert bundle["book"]["title"] == "Los de abajo"
    assert bundle["book"]["author"] == "Mariano Azuela"


def test_report_only_writes_nothing(fixture_epub, tmp_path, capsys):
    exit_code = main([str(fixture_epub), "--out", str(tmp_path), "--no-gloss", "--report-only"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert list(tmp_path.iterdir()) == []
    assert "Molcajete bundle report" in output


def test_thresholds_are_settable_from_the_command_line(fixture_epub, tmp_path, capsys):
    main(
        [
            str(fixture_epub),
            "--out",
            str(tmp_path),
            "--no-gloss",
            "--zipf-threshold",
            "9.0",
            "--min-book-count",
            "99",
        ]
    )
    capsys.readouterr()

    path = tmp_path / f"anonimo-los-del-cerro{BUNDLE_SUFFIX}"
    bundle = json.loads(path.read_text(encoding="utf-8"))
    assert sum(len(c["teachSet"]) for c in bundle["chapters"]) == 0


class TestKnownLemmas:
    def test_no_path_means_no_known_lemmas(self):
        assert load_known_lemmas(None) == frozenset()

    def test_reads_the_flat_array_from_spec_section_8(self, tmp_path):
        path = tmp_path / "known.json"
        path.write_text(json.dumps(["caballo", "Sierra"]), encoding="utf-8")

        assert load_known_lemmas(path) == frozenset({"caballo", "sierra"})

    def test_rejects_anything_that_is_not_a_flat_array(self, tmp_path):
        path = tmp_path / "known.json"
        path.write_text(json.dumps({"lemmas": ["caballo"]}), encoding="utf-8")

        with pytest.raises(ValueError, match="flat array"):
            load_known_lemmas(path)
