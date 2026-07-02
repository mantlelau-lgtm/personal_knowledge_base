from pathlib import Path

import pytest

from common.exceptions import CheckpointError, CollectionError, ConfigError, ParseError, PKBError
from data_collection import parsers
from data_collection.collector import DataCollector
from data_collection.parsers import parse_to_markdown


def test_parse_txt_fallback(settings, tmp_path):
    src = tmp_path / "note.txt"
    src.write_text("hello text", encoding="utf-8")
    md = parse_to_markdown(src)
    assert "# note" in md
    assert "hello text" in md


@pytest.mark.parametrize(
    "name, marker",
    [
        ("broken.pdf", "PDF"),
        ("broken.doc", "Word"),
        ("broken.xlsx", "Excel"),
        ("broken.pptx", "PPT"),
        ("broken.png", "OCR"),
        ("broken.bin", "暂不支持"),
    ],
)
def test_parser_fallbacks_are_explainable(tmp_path, name, marker):
    src = tmp_path / name
    src.write_bytes(b"not a real document")
    md = parse_to_markdown(src)
    assert "解析降级" in md
    assert marker in md


def test_parse_docx_zip_fallback(tmp_path, monkeypatch):
    src = tmp_path / "fake.docx"
    src.write_bytes(b"not a zip")
    monkeypatch.setitem(__import__("sys").modules, "docx", None)
    md = parsers.parse_docx(src)
    assert "解析降级" in md
    assert "Word" in md


def test_collect_markdown(settings, tmp_path):
    src = tmp_path / "note.md"
    src.write_text("# Python\n\npytest knowledge", encoding="utf-8")
    collector = DataCollector(settings)
    result = collector.collect_one(src)
    assert Path(result.raw_path).exists()
    assert Path(result.parsed_path).exists()
    assert Path(result.parsed_path).read_text(encoding="utf-8") == "# Python\n\npytest knowledge"
    skipped = collector.collect_one(src)
    assert skipped.status == "skipped"


def test_collect_directory_and_uploaded_file(settings, tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "a.md").write_text("# A", encoding="utf-8")
    (docs / "b.txt").write_text("B text", encoding="utf-8")
    (docs / "ignore.bin").write_bytes(b"ignore")
    collector = DataCollector(settings)
    results = collector.collect([docs])
    assert len(results) == 2
    uploaded = collector.collect_uploaded_file("upload.txt", b"uploaded text")
    assert Path(uploaded.raw_path).exists()
    assert Path(uploaded.parsed_path).exists()


def test_custom_exceptions_can_be_raised():
    for exc_type in (PKBError, ConfigError, CollectionError, ParseError, CheckpointError):
        with pytest.raises(exc_type):
            raise exc_type("boom")
