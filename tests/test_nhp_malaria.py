"""CBHI National Health Profile 2023, Table 3.1.1: malaria cases and deaths by State/UT."""

import json
import shutil
from pathlib import Path

import pandas as pd
import pytest
from cli_helpers import run

from pdfexorcist.checks import validate
from pdfexorcist.recipe import load

ROOT = Path(__file__).parent.parent
FIXTURES = Path(__file__).parent / "fixtures" / "nhp"
FIXTURE = "nhp_2023_p120.pdf"
RECIPE = ROOT / "pdfexorcist" / "recipes" / "nhp_malaria" / "recipe.toml"
# from pdftotext -layout with a regex, independent of the parser
EXPECTED = pd.read_csv(FIXTURES / "expected.csv", dtype=str, keep_default_na=False)

pytestmark = pytest.mark.usefixtures("wide_console")


@pytest.fixture(scope="module")
def result(tmp_path_factory: pytest.TempPathFactory) -> tuple[int, dict, pd.DataFrame]:
    """(exit code, JSON summary, the CSV table indexed by State) on a copy of the fixture."""
    tmp = tmp_path_factory.mktemp("nhp")
    pdf = tmp / "nhp.pdf"
    shutil.copy(FIXTURES / FIXTURE, pdf)
    r = run(["extract", str(pdf), "--recipe", str(RECIPE), "--json", "-q"])
    table = pd.read_csv(tmp / "nhp.csv", dtype=str, keep_default_na=False)
    return r.exit_code, json.loads(r.stdout), table.set_index("state")


def test_every_value_agreed(result) -> None:
    """Pin every printed value to its State/UT, year and measure."""
    _, s, t = result
    cols = [c for c in t.columns if c != "sno"]
    got = {(st, c): v for st, row in t.iterrows() for c in cols if (v := row[c]) != ""}
    want = {(r.state, r.col): r.value for _, r in EXPECTED.iterrows()}
    assert got == want
    assert s["cells"]["verified"] == len(want) == 374 and s["cells"]["unresolved"] == 0


def test_rows_and_columns(result) -> None:
    """Pin the India row, the provisional year, a wrapped name and the split UT."""
    t = result[2]
    assert t.columns[-2:].tolist() == ["2022 (Prov.) Cases", "2022 (Prov.) Deaths"]
    assert t.loc["India"].tolist()[1:] == [
        "429928", "96", "338494", "77", "186532", "93", "161753", "90", "173975", "64"
    ]  # fmt: skip
    assert t.loc["Andaman & Nicobar Islands", ["sno", "2020 Deaths"]].tolist() == ["29", "2"]
    assert t.loc["Daman & Diu"].tolist()[1:] == ["24", "0", "8", "0", "", "", "", "", "", ""]
    assert t.loc["Chattisgarh", ["2018 Cases", "2018 Deaths"]].tolist() == ["78717", "39"]
    assert t.loc["Maharashtra", "2022 (Prov.) Deaths"] == "25"
    # as printed; swapped-looking in 2021 but the column still adds up
    assert t.loc[["Uttar Pradesh", "Uttarakhand"], "2021 Cases"].tolist() == ["13", "10792"]


def test_states_add_up_to_india(result) -> None:
    """Pin the totals check: it runs on every column and passes."""
    code, s, _ = result
    assert code == 0 and s["cells"]["failed_checks"] == 0
    assert len(s["checks_run"]) == 1


def test_a_wrong_total_is_flagged() -> None:
    """Pin the check failing one column whose India total is off by one."""
    cells = EXPECTED.assign(page=1)
    india = (cells.state == "India") & (cells.col == "2021 Cases")
    cells.loc[india, "value"] = "161754"
    out = validate(cells, load(RECIPE).check_functions())
    assert set(out[out.failed != ""].col) == {"2021 Cases"}
