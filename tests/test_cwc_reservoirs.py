"""CWC reservoir storage bulletin."""

import json
import shutil
from pathlib import Path

import pandas as pd
import pytest
from cli_helpers import run
from cwc_reservoirs import COLS, pct_of_live

ROOT = Path(__file__).parent.parent
FIXTURES = Path(__file__).parent / "fixtures" / "cwc"
FIXTURE = "cwc_2018-02-01.pdf"
RECIPE = ROOT / "pdfexorcist" / "recipes" / "cwc_reservoirs" / "recipe.toml"
EXPECTED = pd.read_csv(FIXTURES / "expected.csv", dtype=str, keep_default_na=False)

pytestmark = pytest.mark.usefixtures("wide_console")


@pytest.fixture(scope="module")
def result(tmp_path_factory: pytest.TempPathFactory) -> tuple[int, dict, pd.DataFrame]:
    """(exit code, JSON summary, the CSV table) of the recipe on a copy of the fixture."""
    tmp = tmp_path_factory.mktemp("cwc")
    pdf = tmp / "cwc.pdf"
    shutil.copy(FIXTURES / FIXTURE, pdf)
    r = run(["extract", str(pdf), "--recipe", str(RECIPE), "--json", "-q"])
    table = pd.read_csv(tmp / "cwc.csv", dtype=str, keep_default_na=False)
    return r.exit_code, json.loads(r.stdout), table


def test_values_tally_with_the_page(result) -> None:
    """Pin every value of the 91 reservoirs and the total."""
    code, s, t = result
    assert code == 0 and s["cells"]["failed_checks"] == 0 and len(s["checks_run"]) == 2
    got = {(r["reservoir"], c): r[c] for _, r in t.iterrows() for c in COLS if r[c] != ""}
    want = {(r["reservoir"], c): r[c] for _, r in EXPECTED.iterrows() for c in COLS if r[c] != ""}
    assert got == want


def test_regions_and_states(result) -> None:
    """Pin region and state headings, carried across pages."""
    t = result[2]
    # "" is the total row
    assert t.region.value_counts().to_dict() == {
        "SOUTHERN": 31, "WESTERN": 27, "EASTERN": 15, "CENTRAL": 12, "NORTHERN": 6, "": 1
    }  # fmt: skip
    t = t.set_index("reservoir")
    assert t.loc["JAYAKWADI(PAITHON)", ["region", "state"]].tolist() == ["WESTERN", "MAHARASHTRA"]
    srisailam = t.loc["SRISAILAM", ["region", "state", "hydel"]].tolist()
    assert srisailam == ["SOUTHERN", "A.P & TG", "*"]
    kabini = t.loc["KABINI(Sancherla Tank)", ["state", "date"]].tolist()
    assert kabini == ["KARNATAKA", "31-01-2018"]
    assert t.loc["ALMATTI", "cca"] == "@"  # the footnote: 425 thousand ha with Narayanpur


def test_pct_check_catches_a_misread() -> None:
    """Pin detection of a live storage read without its leading digit."""
    row = EXPECTED[EXPECTED.reservoir == "UKAI"].iloc[0]
    cells = pd.DataFrame([{"page": 5, "id": "ukai", "col": c, "value": row[c]} for c in COLS])
    assert not pct_of_live(cells).any()
    cells.loc[cells.col == "live", "value"] = "0.523"
    assert set(cells[pct_of_live(cells)].col) == {"live", "live_cap", "pct"}
