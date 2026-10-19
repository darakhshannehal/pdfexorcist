"""NSS KI 75/25.0 (Health), Appendix A: detailed tables with sector side labels."""

import json
import shutil
from pathlib import Path

import pandas as pd
import pytest
from cli_helpers import run
from nss_ki75 import parse, shares_add_up

from pdfexorcist import extract
from pdfexorcist._prepare import crop_pages
from pdfexorcist.rows import parse_rows

ROOT = Path(__file__).parent.parent
FIXTURES = Path(__file__).parent / "fixtures" / "nss_health"
FIXTURE = "nss_ki75_appendix_p68-73.pdf"
REPORT_446 = "nss_446_p18.pdf"
RECIPE = ROOT / "pdfexorcist" / "recipes" / "nss_health" / "recipe.toml"
EXPECTED = pd.read_csv(FIXTURES / "expected.csv", dtype=str, keep_default_na=False)
TEXT_ENGINES = ["pdftotext", "pdfplumber", "pymupdf", "pdfium"]

pytestmark = pytest.mark.usefixtures("wide_console")


@pytest.fixture(scope="module")
def result(tmp_path_factory: pytest.TempPathFactory) -> tuple[int, dict, pd.DataFrame]:
    """(exit code, JSON summary, the CSV table) of the recipe on a copy of the fixture."""
    tmp = tmp_path_factory.mktemp("nss_health")
    pdf = tmp / "ki75.pdf"
    shutil.copy(FIXTURES / FIXTURE, pdf)
    r = run(["extract", str(pdf), "--recipe", str(RECIPE), "--json", "-q"])
    table = pd.read_csv(tmp / "ki75.csv", dtype=str, keep_default_na=False)
    return r.exit_code, json.loads(r.stdout), table


def test_cells_agree(result) -> None:
    """Pin every cell, all agreed, A25's wrapped "Charitable/NGO run" row too."""
    code, s, t = result
    assert code == 0 and (s["cells"]["verified"], s["cells"]["unresolved"]) == (801, 0)
    assert s["cells"]["failed_checks"] == 0 and len(s["checks_run"]) == 1
    pd.testing.assert_frame_equal(t, EXPECTED)


def _row(t: pd.DataFrame, table: str, label: str, **by: str) -> list[str]:
    hit = t[(t.table == table) & (t.label == label)]
    for k, v in by.items():
        hit = hit[hit[k] == v]
    assert len(hit) == 1, (table, label, by)
    return [v for v in hit.iloc[0][[str(c) for c in range(8)]].tolist() if v]


def test_blocks_are_named_by_their_side_labels(result) -> None:
    """Pin the rows that pymupdf and pdfium read with the side label in their first cell."""
    t = result[2]
    assert _row(t, "A23", "private hospital", sector="Rural") == ["1158", "1015", "1081"]
    assert _row(t, "A23", "private hospital", sector="Rural + Urban") == ["1092", "1035", "1062"]
    assert _row(t, "A26", "private hospital", sector="Urban", group="Female")[0] == "17.2"
    assert _row(t, "A31", "Percentage of cases receiving surgery", sector="Urban")[0] == "26.2"
    assert _row(t, "A32", "With spouse and other members", sector="Rural + Urban") == [
        "64.1", "37.0", "50.3"
    ]  # fmt: skip
    assert set(t[t.table == "A25"].sector) == {""}  # one block, no side label


def test_labels_keep_their_numbers_and_headings(result) -> None:
    """Pin "below 20" (A27) and the hospital heading carried to A30's delivery rows."""
    t = result[2]
    assert _row(t, "A27", "below 20") == ["98", "85", "98", "91", "98", "86"]
    assert _row(t, "A27", "45 & above") == ["99", "83", "100", "100", "99", "87"]
    assert _row(t, "A30", "Private hospital: Normal delivery", sector="Urban")[-1] == "17960"


def _labels(lines: list) -> list[tuple[str, str, str]]:
    return [(r["label"], r["sector"], r["area"]) for r in parse([(1, lines)]) if r["col"] == 0]


def test_side_label_forms() -> None:
    """Pin a side label in its own line, in a first cell, joined to the label, and a State."""
    lines = [
        [(0.0, "Table A1: x")],
        [(50.0, "Percentage of cases"), (90.0, "1.0")],
        [(10.0, "Rural")],
        [(10.0, "Female Sterilisation"), (90.0, "2.0")],
        [(50.0, "Percentage of cases"), (90.0, "3.0")],
        [(10.0, "Urban"), (50.0, "Female Sterilisation"), (90.0, "4.0")],
        [(10.0, "Urban Percentage of cases"), (90.0, "5.0")],
    ]
    assert _labels(lines) == [
        ("Percentage of cases", "Rural", ""),
        ("Female Sterilisation", "Rural", ""),  # no block reads "Sterilisation" alone
        ("Percentage of cases", "Urban", ""),
        ("Female Sterilisation", "Urban", ""),
        ("Percentage of cases", "Urban", ""),
    ]
    states = [
        [(0.0, "Table A8: x")],
        [(10.0, "Assam"), (50.0, "public hospital"), (90.0, "50.6")],
        [(50.0, "all"), (90.0, "100.0")],
        [(10.0, "Bihar"), (50.0, "public hospital"), (90.0, "17.8")],
    ]
    assert [x[2] for x in _labels(states)] == ["Assam", "Assam", "Bihar"]


def test_wrapped_label() -> None:
    """Pin values read a line below their label, and a side label never taking their place."""
    lines = [
        [(0.0, "Table A1: x")],
        [(50.0, "Public hospitals"), (90.0, "327")],
        [(50.0, "Charitable/NGO run")],
        [(90.0, "589")],
        [(50.0, "hospitals")],
        [(10.0, "Rural +")],
        [(90.0, "1")],
    ]
    assert [x[0] for x in _labels(lines)] == ["Public hospitals", "Charitable/NGO run"]


def test_default_rows_drop_side_labels_on_the_ki75_fixture() -> None:
    """Pin each A23 private-hospital row to one key that all engines agree on."""
    cells = extract(FIXTURES / FIXTURE, TEXT_ENGINES, pages=[1])
    assert (cells.status == "verified").all()
    got = cells[(cells.row == "privatehospital#1") & (cells.col == 0)].iloc[0]
    assert (got.value, got.votes) == ("1158", "1158×4")


def test_default_rows_carry_a_wrapped_label_on_the_ki75_fixture() -> None:
    """A25's values-only line keeps its first label line as the row key."""
    cells = extract(FIXTURES / FIXTURE, TEXT_ENGINES, pages=[2])
    row = cells[(cells.row == "charitablengorun#1") & (cells.col == 0)].iloc[0]
    assert (row.value, row.status, row.votes) == ("589", "verified", "589×4")


@pytest.fixture(scope="module")
def cropped_446(tmp_path_factory: pytest.TempPathFactory) -> pd.DataFrame:
    """The vote on Table 4.6 cropped away from the prose column beside it."""
    tmp = tmp_path_factory.mktemp("nss_446")
    return extract(crop_pages(FIXTURES / REPORT_446, tmp, (50, 145, 390, 390)), TEXT_ENGINES)


def test_area_crop_removes_the_second_column_before_engines_read_446(cropped_446) -> None:
    """Pin Table 4.6's rows once the area crop drops the prose beside them."""
    cells = cropped_446
    male = cells[cells.row == "male#1"].sort_values("col")
    assert male.value.tolist() == ["485", "180", "313", "1000"]
    assert (cells.status == "verified").all()


def test_unbalanced_bracket_is_reported_as_lossy_on_446(cropped_446) -> None:
    """Pin the printed 457) as kept and failing the lossy check."""
    bad = cropped_446[cropped_446.value == "457)"]
    assert len(bad) == 1 and bad.iloc[0].failed == "lossy value"


def test_shares_check_catches_a_misread(result) -> None:
    """Pin the check: A32's living arrangements add up to 100, and a misread fails them."""
    cells = EXPECTED.melt(
        ["table", "block", "sector", "group", "area", "label", "n", "page"], var_name="col"
    )
    cells = cells[cells.value != ""]
    assert not shares_add_up(cells).any()
    hit = (
        (cells.table == "A32")
        & (cells.label == "Alone")
        & (cells.block == "1")
        & (cells.col == "0")
    )
    assert shares_add_up(cells.assign(value=cells.value.mask(hit, "7.6"))).sum() == 7


@pytest.fixture(scope="module")
def default() -> pd.DataFrame:
    """The default parser's vote on the fixture, with fit_width."""
    return extract(
        FIXTURES / FIXTURE,
        methods=TEXT_ENGINES,
        parse=lambda pages: parse_rows(pages, fit_width=True),
    )


def test_default_parser_agrees(default: pd.DataFrame) -> None:
    """Pin side labels, wrapped labels and "below 20" without the custom parser."""
    assert (default.status == "verified").all() and len(default) == 801
    a23 = default[(default.page == 1) & default.row.str.startswith("privatehospital#")]
    assert a23.groupby("row").value.apply(list).to_dict() == {
        "privatehospital#1": ["1158", "1015", "1081"],
        "privatehospital#2": ["1013", "1062", "1038"],
        "privatehospital#3": ["1092", "1035", "1062"],
    }
    assert default[default.row == "charitablengorun#1"].value.iloc[0] == "589"
    below = default[default.row == "below20#1"].value.tolist()
    assert below == ["98", "85", "98", "91", "98", "86"]
