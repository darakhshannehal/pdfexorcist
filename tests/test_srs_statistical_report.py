"""SRS Statistical Report 2024, Table 1: percent distribution by age, sex and residence."""

import json
import shutil
from pathlib import Path

import pandas as pd
import pytest
from cli_helpers import run
from srs_stat import COLS

from pdfexorcist.checks import validate
from pdfexorcist.recipe import load

ROOT = Path(__file__).parent.parent
FIXTURES = Path(__file__).parent / "fixtures" / "srs_stat"
FIXTURE = "srs_stat_2024_table1_p222-224.pdf"
RECIPE = ROOT / "examples" / "srs_statistical_report" / "recipe.toml"
EXPECTED = pd.read_csv(FIXTURES / "expected.csv", dtype=str, keep_default_na=False)

pytestmark = pytest.mark.usefixtures("wide_console")


@pytest.fixture(scope="module")
def result(tmp_path_factory: pytest.TempPathFactory) -> tuple[int, dict, pd.DataFrame]:
    """(exit code, JSON summary, the CSV table) of the recipe on a copy of the fixture."""
    tmp = tmp_path_factory.mktemp("srs_stat")
    pdf = tmp / "srs.pdf"
    shutil.copy(FIXTURES / FIXTURE, pdf)
    r = run(["extract", str(pdf), "--recipe", str(RECIPE), "--json", "-q"])
    table = pd.read_csv(tmp / "srs.csv", dtype=str, keep_default_na=False)
    return r.exit_code, json.loads(r.stdout), table


def test_every_value_verified(result) -> None:
    """Pin every cell to the pdftotext reading, all agreed."""
    code, s, t = result
    assert code == 0 and s["cells"]["verified"] == 855 and s["cells"]["unresolved"] == 0
    pd.testing.assert_frame_equal(t, EXPECTED)


def test_states_and_values(result) -> None:
    """Pin State headings and cells across the Total, Rural and Urban columns."""
    t = result[2].set_index(["state", "age"])
    assert list(dict.fromkeys(t.index.get_level_values("state"))) == [
        "India", "Andhra Pradesh", "Assam", "Bihar", "Chhattisgarh"
    ]  # fmt: skip
    assert t.loc[("India", "0-4"), ["total_total", "rural_total", "urban_total"]].tolist() == [
        "7.9", "8.6", "6.6"
    ]  # fmt: skip
    assert t.loc[("Assam", "20-24"), "rural_females"] == "12.1"
    assert t.loc[("Bihar", "0-4"), "total_males"] == "11.8"
    assert t.loc[("Andhra Pradesh", "85+"), "urban_females"] == "0.4"
    assert (t.xs("Total", level="age")[COLS] == "100.0").all().all()


def test_checks_pass_and_catch_a_misread(result) -> None:
    """Pin both checks: they pass as printed and flag a misread 7 and a value outside its parts."""
    assert result[1]["cells"]["failed_checks"] == 0 and len(result[1]["checks_run"]) == 2
    checks = load(RECIPE).check_functions()
    cells = EXPECTED.melt(["state", "age"], var_name="col").assign(page=1, block=lambda d: d.state)

    def flagged(state: str, age: str, col: str, value: str) -> set[str]:
        hit = (cells.state == state) & (cells.age == age) & (cells.col == col)
        out = validate(cells.assign(value=cells.value.mask(hit, value)), checks)
        return set(out.loc[out.failed != "", "failed"].str.split("; ").explode())

    assert flagged("India", "20-24", "total_total", "10.1") == {"age groups add up to 100"}
    assert flagged("India", "0-4", "total_total", "6.4") == {
        "age groups add up to 100", "total lies outside its two parts"
    }  # fmt: skip
