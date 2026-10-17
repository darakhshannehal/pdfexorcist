"""Gaps found verifying the CRS reports (gaps.md): one test per mechanism.

Expected values are read off 200 dpi renders of the printed pages.
"""

import shutil
from functools import cache, partial
from pathlib import Path

import pandas as pd
import pytest

from pdfexorcist import extract, parse_by_columns, parse_rows
from pdfexorcist._bold import debold_line, one_value
from pdfexorcist._slanted import _chars, drop_slanted
from pdfexorcist.extractors import EXTRACTORS
from pdfexorcist.pages import find
from pdfexorcist.rows import is_value

FIXTURES = Path(__file__).parent / "fixtures" / "crs"
needs_tesseract = pytest.mark.skipif(not shutil.which("tesseract"), reason="needs tesseract")


@cache
def _voted(name: str, placement: str = "") -> pd.DataFrame:
    """extract() of a fixture, read once per session."""
    parse = partial(parse_by_columns, placement=placement) if placement else parse_rows
    return extract(FIXTURES / name, parse=parse)


def _printed(values: str) -> dict[int, str]:
    """Values as printed, left to right, by column."""
    return dict(enumerate(values.split()))


def _row(res: pd.DataFrame, row: str, page: int = 1) -> dict[int, str]:
    """Verified values of one row, by column."""
    r = res[(res.page == page) & (res.row == row) & (res.status == "verified")]
    return dict(zip(r.col, r.value, strict=True))


def test_g1_diagonal_text_no_longer_chains_rows() -> None:
    """2010 p69: "Not Available" drawn at 30 degrees across the Urban cells."""
    res = _voted("crs_2010_t6_diagonal.pdf")
    assert (res.status != "verified").sum() == 0
    assert "25year34year#1" in set(res.row)  # the slanted text's letters join no label
    assert _row(res, "bihar#1") == _printed("29568 73288 102856 49 5800 5849 29617 79088 108705")
    assert _row(res, "70yearabove#1") == {0: "50950", 1: "42153", 2: "93103"}


def test_g1_slanted_text_over_level_text_keeps_the_level_text(tmp_path: Path) -> None:
    """2016 p101: a slanted dot leader overlaps an upright N.A., which must stay."""
    import pymupdf

    pdf = FIXTURES / "crs_2016_district_rotated.pdf"
    with pymupdf.open(pdf) as before, pymupdf.open(drop_slanted(pdf, tmp_path)) as after:
        for a, b in zip(before, after, strict=True):
            assert _chars(a)[0] == _chars(b)[0]  # level text as printed
            assert len(_chars(b)[1]) < len(_chars(a)[1]) / 4  # most slanted text gone


def test_g2_fake_bold_rows_are_read_once() -> None:
    """2023 p105: bold rows drawn four times."""
    res = _voted("crs_2023_t6_fakebold.pdf")
    assert (res.status != "verified").sum() == 0
    assert not res.row.str.contains("delhidelhi|ladakhladakh").any()
    assert _row(res, "delhi#1") == _printed(
        "16093 9181 25277 65407 41687 107114 81500 50868 132391"
    )
    assert _row(res, "ladakh#1") == _printed("388 198 586 260 106 366 648 304 952")


def test_g2_text_fallback_never_shortens_a_plain_rows_digits() -> None:
    """De-bolding takes k from the label; a plain row keeps 11110 and 111121."""
    plain = [(0, "Goa"), (10, "11110"), (20, "111121")]
    assert debold_line(plain, is_value) == plain
    bold = [(0, "GGGGooooaaaa"), (10, "1" * 16 + "0" * 4), (20, "388 388 388 388")]
    assert [t for _, t in debold_line(bold, is_value)] == ["Goa", "11110", "388"]
    assert [t for _, t in debold_line([(0, "Delhi Delhi"), (9, "1616")], is_value)] == [
        "Delhi",
        "16",
    ]
    assert one_value("366 366366", is_value) == "366"
    assert one_value("366366", is_value) == "366366"  # one token: as printed


def test_g3_pdftotext_splits_values_in_narrow_columns() -> None:
    """2019 p67: pdftotext reads "947 947 948 949 953 953" as six cells."""
    lines = [
        ln
        for _, page in EXTRACTORS["pdftotext"](FIXTURES / "crs_2019_t6_squeezed.pdf")
        for ln in page
    ]
    row = next(ln for ln in lines if [t for _, t in ln][:3] == ["942", "947", "947"])
    assert [t for _, t in row] == ["942", "947", "947", "948", "949", "953", "953"]
    xs = [x for x, _ in row]
    assert xs == sorted(xs) and len(set(xs)) == len(xs)


def test_g5_excel_rounded_values_fail_the_lossy_check() -> None:
    """2011: 2E+05 is read and fails the lossy check (Gujarat's is 161678)."""
    res = _voted("crs_2011_t6_excel.pdf")
    lossy = res[res.failed.str.contains("lossy value")]
    assert sorted(zip(lossy.page, lossy.row, lossy.value, strict=True)) == [
        (1, "gujarat#1", "2E+05"),
        (2, "karnataka#1", "2E+05"),
        (3, "rajasthan#1", "1E+05"),
        (4, "delhi#1", "1E+05"),
    ]
    assert set(lossy.col) == {5}  # Urban Person


def test_g6_order_alone_shifts_a_partial_row() -> None:
    """2010 Table 4: J&K prints Not Available over Rural; by order its Urban values land there."""
    res = _voted("crs_2010_t4_partial.pdf")
    jk = _row(res, "jammukashmirnotavailable#1")
    assert jk[0] == "739"  # printed under Urban Male: the shift G6 guards against


def test_g6_both_placements_must_agree() -> None:
    """placement="both" keeps only cells where order and x agree, and shows both readings."""
    res = _voted("crs_2010_t4_partial.pdf", "both")
    hp, jk = "himachalpradeshnotavailable#1", "jammukashmirnotavailable#1"
    assert _row(res, hp) == {0: "28", 1: "23", 2: "51"}  # Rural; Urban is Not Available
    assert _row(res, jk) == {3: "739", 4: "884", 5: "1623"}  # Urban; Rural is Not Available
    cell = res[(res.row == hp) & (res.col == 6)].iloc[0]  # Total Male: 28, read 6th by order
    assert cell.status == "unresolved" and "pymupdf=blank/28" in cell.dissent
    full = res[res.row == "gujarat#1"]
    assert (full.status == "verified").all() and len(full) == 9


@needs_tesseract
def test_g4_type3_fonts_are_decoded() -> None:
    """2017: Type3 fonts without ToUnicode; all text engines read text after the glyph map."""
    res = _voted("crs_2017_type3.pdf")
    assert _row(res, "andhrapradesh#1") == {0: "96.5", 1: "94.4"}
    ahmadabad = _row(res, "1ahmadabad#1", page=2)
    assert ahmadabad == _printed("4827 3269 8096 30469 21478 51947 35296 24747 60043")
    assert (res.status == "verified").sum() >= 670


@needs_tesseract
def test_g7_find_pages_by_title_ocr() -> None:
    """2017: the titles are Type3 control codes; find() reads the top strip by OCR."""
    pdf = FIXTURES / "crs_2017_type3.pdf"
    assert find(pdf, r"TABLE\s*-?\s*8\s*:") == [2]
    assert find(pdf, r"TABLE\s*-?\s*5\s*:") == [1]
    assert find(pdf, r"TABLE\s*-?\s*8\s*:", ocr_fallback=False) == []
