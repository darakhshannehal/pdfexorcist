"""CPCB AQI bulletin."""

import json
import shutil
from pathlib import Path

import pandas as pd
import pytest
from cli_helpers import run
from cpcb_aqi import category_band

ROOT = Path(__file__).parent.parent
FIXTURE = Path(__file__).parent / "fixtures" / "cpcb" / "cpcb_aqi_2026-10-18_p1-2_14-15.pdf"
RECIPE = ROOT / "pdfexorcist" / "recipes" / "cpcb_aqi" / "recipe.toml"

pytestmark = pytest.mark.usefixtures("wide_console")


@pytest.fixture(scope="module")
def result(tmp_path_factory: pytest.TempPathFactory) -> tuple[int, dict, pd.DataFrame]:
    """(exit code, JSON summary, the CSV table) of the recipe on a copy of the fixture."""
    tmp = tmp_path_factory.mktemp("cpcb")
    pdf = tmp / "aqi.pdf"
    shutil.copy(FIXTURE, pdf)
    r = run(["extract", str(pdf), "--recipe", str(RECIPE), "--json", "-q"])
    table = pd.read_csv(tmp / "aqi.csv", dtype=str, keep_default_na=False)
    return r.exit_code, json.loads(r.stdout), table.set_index("city")


def test_every_city_agreed(result) -> None:
    """Pin the 53 cities on the three table pages; the last page has none."""
    code, s, t = result
    assert code == 0 and s["cells"]["failed_checks"] == 0 and len(s["checks_run"]) == 2
    assert s["pages"] == [1, 2, 3] and s["cells"]["verified"] == s["cells"]["total"] == 53 * 6
    assert t.sr.astype(int).tolist() == [*range(1, 41), *range(261, 274)]


def test_values(result) -> None:
    """Pin the date and time, cities, a wrapped name, and pollutants with subscripts."""
    t = result[2]
    assert set(zip(t.date, t.time, strict=True)) == {
        ("2026-10-18", "16:00")
    }  # the title, every page
    assert t.loc["Agartala"].tolist() == [
        "2026-10-18",
        "16:00",
        "1",
        "Moderate",
        "158",
        "PM10",
        "1",
        "2",
    ]
    assert t.loc["Aurangabad (Maharashtra)"].tolist() == [
        "2026-10-18",
        "16:00",
        "21",
        "Satisfactory",
        "94",
        "PM2.5, PM10, O3",
        "3",
        "3",
    ]
    assert t.loc["Ballabgarh", ["category", "aqi"]].tolist() == ["Poor", "278"]
    assert t.loc["Yamuna nagar", "aqi"] == "162"


def test_band_check_catches_a_misread() -> None:
    """Pin detection of an AQI outside its category."""
    vals = {"category": "Moderate", "aqi": "158"}
    cells = pd.DataFrame(
        [{"page": 1, "id": "agartala", "col": c, "value": v} for c, v in vals.items()]
    )
    assert not category_band(cells).any()
    cells.loc[cells.col == "aqi", "value"] = "58"
    assert set(cells[category_band(cells)].col) == {"aqi", "category"}
