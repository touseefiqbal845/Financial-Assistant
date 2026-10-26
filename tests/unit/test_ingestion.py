import pytest

from financial_assistant.ingestion.pipeline import chunks, parse_document


def test_ingestion_rejects_path_escape_and_large_files(tmp_path):
    root = tmp_path / "input"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("private")
    with pytest.raises(ValueError):
        parse_document(outside, root)
    oversized = root / "large.txt"
    oversized.write_text("x" * 2_000_001)
    with pytest.raises(ValueError):
        parse_document(oversized, root)


def test_pages_and_bounded_chunks_preserved(tmp_path):
    source = tmp_path / "notes.md"
    source.write_text("  synthetic\n  management notes  ")
    assert chunks(parse_document(source, tmp_path)) == [(1, "synthetic management notes")]
    with pytest.raises(ValueError):
        chunks([(1, " ")])
