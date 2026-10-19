"""Space glyphs drawn over letters must not split words ("Bombay d u c k", IFCT 2017 p195)."""

import pymupdf
import pytest

from pdfexorcist.extractors import EXTRACTORS


def _spaced_pdf(path):
    doc = pymupdf.open()
    page = doc.new_page(width=300, height=100)
    page.insert_text((20, 50), "Bombay", fontname="helv", fontsize=10)  # registers /helv
    xref = page.get_contents()[0]
    # 278 pulls back one space width, so each space sits under the next letter
    tj = b"BT /helv 10 Tf 70 50 Td [(d ) 278 (u ) 278 (c ) 278 (k)] TJ ET"
    doc.update_stream(
        xref, doc.xref_stream(xref) + b"\n" + tj + b"\nBT /helv 10 Tf 150 50 Td (42) Tj ET"
    )
    doc.save(path)


@pytest.mark.parametrize("engine", ["pdfplumber", "pymupdf", "pdfium"])
def test_overprinted_spaces_do_not_split_words(tmp_path, engine):
    pdf = tmp_path / "spaced.pdf"
    _spaced_pdf(pdf)
    ((_, lines),) = list(EXTRACTORS[engine](pdf))
    assert [t for line in lines for _, t in line] == ["Bombay", "duck", "42"]


def test_plain_spaces_still_split_words(tmp_path):
    pdf = tmp_path / "plain.pdf"
    doc = pymupdf.open()
    doc.new_page(width=300, height=100).insert_text((20, 50), "Bombay duck", fontsize=10)
    doc.save(pdf)
    for engine in ("pymupdf", "pdfium"):
        ((_, lines),) = list(EXTRACTORS[engine](pdf))
        assert " ".join(t for line in lines for _, t in line) == "Bombay duck", engine
