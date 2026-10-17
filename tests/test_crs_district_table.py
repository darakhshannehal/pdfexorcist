"""CRS District Tables 7-10."""

import shutil
from functools import cache
from pathlib import Path

import pandas as pd
import pytest
from crs_district_table import KEY, parse

from pdfexorcist import extract, total_check, validate

FIXTURES = Path(__file__).parent / "fixtures" / "crs"
CHECKS = [  # as recipe.toml
    total_check(
        "sex", "Person", ["Male", "Female"], by=["page", "state", "district", "area"], op=">="
    ),
    total_check(
        "area", "Total", ["Rural", "Urban"], by=["page", "state", "district", "sex"], op=">="
    ),
    total_check(
        "level", "State", ["District"], by=["table", "state", "col"], op=">=", where="col != 'SRB'"
    ),
]


@cache
def _voted(fixture: str) -> pd.DataFrame:
    """The recipe's parser and checks on a fixture."""
    res = extract(FIXTURES / fixture, parse=parse, key=KEY)
    ok = res.status == "verified"
    res["failed"] = validate(res[ok], CHECKS)["failed"].reindex(res.index, fill_value="")
    return res


def _district(res: pd.DataFrame, page: int, district: str) -> dict[str, str]:
    d = res[(res.page == page) & (res.district == district) & (res.status == "verified")]
    return dict(zip(d.col, d.value, strict=True))


def test_slanted_not_available_pages() -> None:
    """2016 p90 (Table 7, with SRB) and p101 (Table 8), "Not Available" at 45 degrees."""
    res = _voted("crs_2016_district_rotated.pdf")
    assert (res.failed == "").all()
    assert (res.status == "verified").mean() > 0.97  # the rest: hidden N.A. text under Manipur
    assert _district(res, 1, "malkangiri") == {
        "Rural_Male": "5192",
        "Rural_Female": "5007",
        "Rural_Person": "10199",
        "Urban_Male": "2076",
        "Urban_Female": "1902",
        "Urban_Person": "3978",
        "Total_Male": "7268",
        "Total_Female": "6909",
        "Total_Person": "14177",
        "SRB": "951",
    }
    assert _district(res, 2, "cuttack")["Total_Person"] == "31433"


def test_a_page_that_goes_on_with_a_state_not_read() -> None:
    """p101 opens with Maharashtra's district 5; its State row is on a page not read."""
    res = _voted("crs_2016_district_rotated.pdf")
    bhandara = res[(res.page == 2) & (res.district == "bhandara")]
    assert set(bhandara.state) == {""} and (bhandara.status == "verified").all()
    assert set(bhandara.serial) == {5}


@pytest.mark.skipif(not shutil.which("tesseract"), reason="needs tesseract")
def test_type3_district_page() -> None:
    """2017 p100: Type3 fonts read by OCR; Ahmadabad as printed."""
    res = _voted("crs_2017_type3.pdf")
    ahmadabad = _district(res, 2, "ahmadabad")
    assert list(ahmadabad.values()) == [
        "4827",
        "3269",
        "8096",
        "30469",
        "21478",
        "51947",
        "35296",
        "24747",
        "60043",
    ]
    assert (res.failed == "").all()
