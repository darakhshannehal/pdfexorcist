"""CRS tables."""

from functools import cache
from pathlib import Path

import pandas as pd
from crs_state_t6 import KEY as T6_KEY
from crs_state_t6 import parse as parse_t6
from crs_state_table import KEY, checks, parse

from pdfexorcist import extract, total_check, validate

FIXTURES = Path(__file__).parent / "fixtures" / "crs"
FIXTURE = "crs_2023_t1_t4.pdf"
EXPECTED = pd.read_csv(FIXTURES / "expected.csv", dtype=str, keep_default_na=False)

# Share of expected cells the vote must agree on, with slack for an engine
# upgrade that loses a row.
MIN_COVERAGE = 0.95

Cell = tuple[int, str, str]  # page, state key, col


@cache
def _voted() -> pd.DataFrame:
    """extract() result for the fixture, read once per session."""
    return extract(FIXTURES / FIXTURE, parse=parse, key=KEY, checks=checks())


def test_vote_tallies_with_expected() -> None:
    """Pin correct agreed values and coverage."""
    res = _voted()
    ok = res[res.status == "verified"]
    got: dict[Cell, str] = {(int(r.page), r.state, r.col): r.value for r in ok.itertuples()}
    want: dict[Cell, str] = {
        (int(r.page), r.state_key, r.col): r.value for r in EXPECTED.itertuples()
    }
    tallied = [k for k in want if k in got]
    wrong = {k: (got[k], want[k]) for k in tallied if got[k] != want[k]}
    missing = [k for k in want if k not in got]
    print(
        f"\n{FIXTURE}: {len(got)} agreed, {len(tallied)} tallied, {len(wrong)} wrong, "
        f"{len(missing)} of {len(want)} missing ({res.n_agree.min()}+ engines per cell)"
    )
    assert wrong == {}
    assert len(tallied) / len(want) >= MIN_COVERAGE


def test_table_arithmetic_holds() -> None:
    """Pin Person and Total arithmetic checks."""
    res = _voted()
    failed = res[res.failed != ""]
    assert failed.empty, failed[[*KEY, "value", "failed"]].to_string()


def test_arithmetic_catches_a_misread() -> None:
    """Pin both checks for a tenfold Bihar misread."""
    res = _voted()
    bad = res[res.status == "verified"].copy()
    at = bad.index[(bad.page == 1) & (bad.state == "bihar") & (bad.col == "Rural_Male")][0]
    assert bad.loc[at, "value"] == "916009"
    bad.loc[at, "value"] = "9160090"
    failed = validate(bad, checks()).failed[at]
    assert "Person >= Male + Female" in failed and "Total >= Rural + Urban" in failed


def test_wrapped_name_and_fake_bold_row() -> None:
    """Pin wrapped-name recovery and fake-bold India (each glyph drawn four times)."""
    res = _voted()
    dnhdd = res[(res.page == 1) & (res.state == "dadraandnagarhavelianddamananddiu")]
    assert set(dnhdd.label) == {"Dadra and Nagar Haveli and Daman and Diu"}
    assert dict(zip(dnhdd.col, dnhdd.value, strict=True))["Total_Person"] == "12948"
    assert (dnhdd.status == "verified").all()
    india = res[res.state == "india"].set_index(["page", "col"])
    assert len(india) == 18 and (india.status == "verified").all()
    assert india.value[(1, "Total_Person")] == "25207070"  # read off the page
    assert india.value[(2, "Rural_Male")] == "19446"


T6_CHECKS = [  # as table6.toml
    total_check("sex", "Person", ["Male", "Female"], by=["page", "state", "age", "area"], op=">="),
    total_check("area", "Total", ["Rural", "Urban"], by=["page", "state", "age", "sex"], op=">="),
    total_check("age", "All Ages", by=["state", "col"], name="All Ages = rest"),
]


@cache
def _t6(fixture: str) -> pd.DataFrame:
    """Table 6 recipe parser and checks on a fixture."""
    res = extract(FIXTURES / fixture, parse=parse_t6, key=T6_KEY)
    ok = res.status == "verified"
    res["failed"] = validate(res[ok], T6_CHECKS)["failed"].reindex(res.index, fill_value="")
    return res


def test_t6_fake_bold_ages_add_up() -> None:
    """2023: every age row of Delhi, J&K, Ladakh, Lakshadweep and Puducherry; all checks hold."""
    res = _t6("crs_2023_t6_fakebold.pdf")
    assert (res.status == "verified").all() and (res.failed == "").all()
    assert set(res.state) == {"delhi", "jammukashmir", "ladakh", "lakshadweep", "puducherry"}
    delhi = res[res.state == "delhi"].set_index(["age", "col"]).value
    assert delhi[("All Ages", "Total_Person")] == "132391"
    assert delhi[("<1", "Urban_Male")] == "3493"
    assert len(res[res.state == "delhi"].age.unique()) == 12  # All Ages and 11 age groups


def test_t6_not_available_is_never_shifted() -> None:
    """2010: Andhra Pradesh prints only Total; its values must not land in Rural."""
    res = _t6("crs_2010_t6_diagonal.pdf")
    ap = res[(res.state == "andhrapradesh") & (res.status == "verified")]
    assert ap.empty  # order says Rural, position says Total: left for review
    bihar = res[res.state == "bihar"].set_index(["age", "col"]).value
    assert bihar[("All Ages", "Urban_Male")] == "49"
    # the page prints "-" for Total Male under 5, so its ages miss the All Ages total
    failed = res[res.failed.str.contains("All Ages")]
    assert set(zip(failed.state, failed.col, strict=True)) >= {("bihar", "Total_Male")}


def test_t6_excel_rounding_is_flagged() -> None:
    """2011: Gujarat's All Ages Urban Person is printed 2E+05: verified, but it fails."""
    res = _t6("crs_2011_t6_excel.pdf")
    cell = res.set_index(["state", "age", "col"]).loc[("gujarat", "All Ages", "Urban_Person")]
    assert cell.value == "2E+05" and cell.status == "verified"
    assert "All Ages = rest" in cell.failed  # 200000 is not the 161678 its ages add up to
