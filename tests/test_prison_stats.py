"""NCRB Prison Statistics India 2023: Tables 1.2 and 1.3, one split over three pages."""

from pathlib import Path

import pandas as pd
import pytest

from pdfexorcist import extract, validate
from pdfexorcist.recipe import load

ROOT = Path(__file__).parent.parent
FIXTURES = Path(__file__).parent / "fixtures" / "prison_stats"
FIXTURE = FIXTURES / "psi_2023_p58-61.pdf"
RECIPE = ROOT / "pdfexorcist" / "recipes" / "prison_stats" / "recipe.toml"

WANT = pd.read_csv(FIXTURES / "expected.csv", dtype=str, keep_default_na=False)


@pytest.fixture(scope="module")
def res() -> pd.DataFrame:
    """extract() cells for the fixture, with the recipe's parser and checks."""
    recipe = load(RECIPE)
    parse, key = recipe.parse_and_key()
    return extract(FIXTURE, parse=parse, key=key, checks=recipe.check_functions())


@pytest.fixture(scope="module")
def table(res: pd.DataFrame) -> pd.DataFrame:
    """One row per State/UT, as the recipe's table output."""
    t = res.pivot_table(index="state", columns="column", values="value", aggfunc="first")
    t = t.reindex(index=WANT.state, columns=WANT.columns[1:], fill_value="")
    return t.assign(section=res.groupby("state").section.first())


def test_every_value_verified(res: pd.DataFrame, table: pd.DataFrame) -> None:
    """Pin every column of every State/UT and total row, every check passing."""
    pd.testing.assert_frame_equal(
        table.drop(columns="section").reset_index(), WANT, check_names=False
    )
    assert (res.status == "verified").all() and (res.failed == "").all()


def test_split_table_joins_by_column_number(table: pd.DataFrame) -> None:
    """Pin values from each page of Table 1.3 on one row, and its totals against Table 1.2."""
    t = table
    assert t.loc["UTTARAKHAND", ["sub_capacity", "sub_inmates", "sub_occupancy"]].tolist() == [
        "799", "2010", "251.6"
    ]  # fmt: skip
    assert t.loc["MIZORAM", "women_occupancy"] == "227.1"
    assert t.loc["WEST BENGAL", "special_inmates"] == "1157"
    india = t.loc["TOTAL (ALL-INDIA)"]
    assert india[["capacity", "inmates", "occupancy"]].tolist() == ["439119", "530333", "120.8"]
    assert india[["all_capacity", "all_inmates", "all_occupancy"]].tolist() == [
        "439119", "530333", "120.8"
    ]  # fmt: skip
    assert t.loc["DELHI", "occupancy"] == "200.2" and t.loc["LAKSHADWEEP", "occupancy_f"] == "-"
    assert t.loc["TOTAL (UTs)", "section"] == "total" and t.loc["DELHI", "section"] == "ut"


def test_checks_catch_a_misread(res: pd.DataFrame) -> None:
    """Pin four checks on a misread of Delhi's inmate total (20077 read as 20777)."""
    bad = res.copy()
    at = bad.index[(bad.page == 1) & (bad.row == "delhi") & (bad.column == "inmates")][0]
    assert bad.loc[at, "value"] == "20077"
    bad.loc[at, "value"] = "20777"
    failed = validate(bad, load(RECIPE).check_functions()).failed[at]
    for name in ("group 'Total'", "row 'totaluts'", "table '1.3'", "occupancy ="):
        assert name in failed, failed
