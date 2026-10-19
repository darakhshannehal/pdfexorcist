"""IDSP weekly outbreak report."""

import json
import shutil
from pathlib import Path

import pandas as pd
import pytest
from cli_helpers import run

ROOT = Path(__file__).parent.parent
FIXTURES = Path(__file__).parent / "fixtures" / "idsp_outbreaks"
FIXTURE = FIXTURES / "idsp_outbreaks_2026_week09_p3-4_11_27-28_31_35-36.pdf"
RECIPE = ROOT / "pdfexorcist" / "recipes" / "idsp_outbreaks" / "recipe.toml"

pytestmark = pytest.mark.usefixtures("wide_console")


@pytest.fixture(scope="module")
def result(tmp_path_factory: pytest.TempPathFactory) -> tuple[int, dict, pd.DataFrame]:
    """(exit code, JSON summary, the CSV table) of the recipe on a copy of the fixture."""
    tmp = tmp_path_factory.mktemp("outbreaks")
    pdf = tmp / "ob.pdf"
    shutil.copy(FIXTURE, pdf)
    r = run(["extract", str(pdf), "--recipe", str(RECIPE), "--json", "-q"])
    table = pd.read_csv(tmp / "ob.csv", dtype=str, keep_default_na=False)
    return r.exit_code, json.loads(r.stdout), table.set_index("id")


def test_every_outbreak_agreed(result) -> None:
    """Pin the 17 outbreaks on the fixture's pages, 5 of them reported late."""
    code, s, t = result
    assert code == 0 and s["cells"]["failed_checks"] == 0 and len(s["checks_run"]) == 1
    assert s["cells"]["verified"] == s["cells"]["total"] == 131
    assert t.table.value_counts().to_dict() == {"week": 12, "late": 5}
    assert set(t.status) == {"Under Control", "Under Surveillance"}


def test_names_as_printed(result) -> None:
    """Pin names joined from wrapped lines and from words broken without a hyphen."""
    t = result[2]
    assert t.loc["AP/ANA/2026/9/304", ["district", "disease"]].tolist() == [
        "Ananthapuramu", "Acute Diarrhoeal Disease"
    ]  # fmt: skip
    assert t.loc["WB/PAR/2026/9/355", ["district", "disease"]].tolist() == [
        "24 Paraganas South", "Suspected Food Poisoning"
    ]  # fmt: skip
    assert t.loc["MH/CHH/2026/9/368", ["state", "district"]].tolist() == [
        "Maharashtra", "Chhatrapati Sambhajinagar"
    ]  # fmt: skip
    assert "Acute Gastroenteritis" in set(t.disease)
    assert t.loc["RJ/BHI/2026/9/370", "disease"] == "Hepatitis A & E"


def test_values(result) -> None:
    """Pin numbers and dates joined across lines; a late outbreak has no reporting date."""
    t = result[2]
    row = t.loc["AP/ANA/2026/9/303"]
    assert row[["cases", "deaths", "start", "reported"]].tolist() == [
        "14", "0", "24-02-2026", "28-02-2026"
    ]  # fmt: skip
    late = t.loc["MG/EAS/2026/9/369"]
    assert late[["cases", "deaths", "start", "reported"]].tolist() == ["2", "2", "24-01-2026", ""]
