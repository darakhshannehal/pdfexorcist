"""Karnataka IDSP weekly infectious disease report."""

import json
import shutil
from pathlib import Path

import pandas as pd
import pytest
from cli_helpers import run

ROOT = Path(__file__).parent.parent
FIXTURE = Path(__file__).parent / "fixtures" / "karnataka_idsp" / "karnataka_idsp_2026_week41.pdf"
RECIPE = ROOT / "pdfexorcist" / "recipes" / "karnataka_idsp" / "recipe.toml"
DISEASES = [
    "SARI", "Influenza", "Acute Diarrhoeal Diseases (ADD)", "Dog Bites & Human Rabies Deaths",
    "Snake bites", "Leptospirosis", "Kyasanur Forest Disease (KFD)", "Dengue", "Chikungunya",
    "Malaria", "Japanese Encephalitis (JE)", "Diphtheria", "Measles", "COVID-19",
]  # fmt: skip

pytestmark = pytest.mark.usefixtures("wide_console")


@pytest.fixture(scope="module")
def result(tmp_path_factory: pytest.TempPathFactory) -> tuple[int, dict, pd.DataFrame]:
    """(exit code, JSON summary, the CSV table) of the recipe on a copy of the fixture."""
    tmp = tmp_path_factory.mktemp("idsp")
    pdf = tmp / "idsp.pdf"
    shutil.copy(FIXTURE, pdf)
    r = run(["extract", str(pdf), "--recipe", str(RECIPE), "--json", "-q"])
    table = pd.read_csv(tmp / "idsp.csv", dtype=str, keep_default_na=False)
    return r.exit_code, json.loads(r.stdout), table


def test_every_disease_by_name(result) -> None:
    """Pin the 14 diseases as printed, in order, every cell agreed."""
    code, s, t = result
    assert code == 0 and s["cells"]["failed_checks"] == 0 and len(s["checks_run"]) == 1
    assert s["cells"]["verified"] == s["cells"]["total"] == 48
    assert list(dict.fromkeys(t.disease)) == DISEASES
    assert set(t.week) == {"41"}


def test_values(result) -> None:
    """Pin values beside the charts, last month for malaria, and the Indian commas."""
    t = result[2].set_index(["disease", "measure"])
    assert t.loc[("SARI", "cases"), ["last_week", "current_year"]].tolist() == ["307", "8050"]
    assert t.loc[("Dog Bites & Human Rabies Deaths", "deaths"), "current_year"] == "47"
    assert t.loc[("Malaria", "tested"), ["last_week", "last_month", "current_year"]].tolist() == [
        "", "1189515", "9529475"
    ]  # fmt: skip
    assert t.loc[("Measles", "reported cases"), "current_year"] == "1714"
    assert t.loc[("COVID-19", "positives"), "current_year"] == "288"
