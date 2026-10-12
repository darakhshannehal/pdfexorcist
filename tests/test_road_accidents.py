"""MoRTH Road Accidents in India 2022: State/UT tables printed sideways."""

import json
import shutil
from pathlib import Path

import pandas as pd
import pytest
from cli_helpers import run
from morth import COLUMNS, parse, rank

ROOT = Path(__file__).parent.parent
FIXTURES = Path(__file__).parent / "fixtures" / "road_accidents"
FIXTURE = "morth_ra_2022_annexure_p136-138.pdf"
RECIPE = ROOT / "examples" / "road_accidents" / "recipe.toml"
ROWS = ["measure", "name"]

pytestmark = pytest.mark.usefixtures("wide_console")


@pytest.fixture(scope="module")
def result(tmp_path_factory: pytest.TempPathFactory) -> tuple[int, dict, pd.DataFrame, Path]:
    """(exit code, JSON summary, CSV table, its folder) of the recipe on a copy of the fixture."""
    tmp = tmp_path_factory.mktemp("road_accidents")
    pdf = tmp / "ra.pdf"
    shutil.copy(FIXTURES / FIXTURE, pdf)
    r = run(["extract", str(pdf), "--recipe", str(RECIPE), "--json", "-q"])
    table = pd.read_csv(tmp / "ra.csv", dtype=str, keep_default_na=False)
    return r.exit_code, json.loads(r.stdout), table, tmp


def test_every_value_verified(result) -> None:
    """All three tables, every cell agreed by all five engines, as in expected.csv."""
    _, s, t, _ = result
    want = pd.read_csv(FIXTURES / "expected.csv", dtype=str, keep_default_na=False)
    pd.testing.assert_frame_equal(t, want)
    assert s["cells"] == {"total": 1774, "verified": 1774, "unresolved": 0, "failed_checks": 1}
    assert s["agreement"] == {"5": 1774}


def test_values_as_printed(result) -> None:
    """Pin real cells, the totals, and the blank and placeholder cells."""
    t = result[2].set_index(ROWS)
    assert t.loc[("killed", "Total"), ["2019", "2020", "2021", "2022"]].tolist() == [
        "158984", "138383", "153972", "168491"
    ]  # fmt: skip
    assert t.loc[("accidents", "Total"), "2022"] == "461312"
    assert t.loc[("injured", "Total"), "per_lakh_pop_2022"] == "32.2"
    assert t.loc[("killed", "Uttar Pradesh"), ["2022", "rank_2022"]].tolist() == ["22595", "1"]
    assert t.loc[("killed", "Tamil Nadu"), "per_lakh_pop_2022"] == "23.3"
    assert t.loc[("accidents", "Haryana"), "per_10k_km_roads_2019"] == "2176.1"
    assert t.loc[("injured", "Kerala"), "per_lakh_pop_2021"] == "103.6"  # pdftotext joins it
    assert t.loc[("killed", "Telangana"), ["per_lakh_pop_2019", "per_lakh_pop_2021"]].tolist() == [
        "#", "20.0"
    ]  # fmt: skip
    daman = t.loc[("killed", "Daman & Diu")]
    assert daman[["2019", "2020", "share_2019", "share_2020"]].tolist() == ["28", "$", "0.0", ""]
    ladakh = t.loc[("killed", "Ladakh")]
    assert ladakh[["2019", "2021", "rank_2022", "per_lakh_pop_2022"]].tolist() == [
        "NA", "56", "", "20.7"
    ]  # fmt: skip


def test_checks(result) -> None:
    """States add up to the Total in every year; one printed share is off."""
    code, s, _, tmp = result
    assert code == 1 and "States/UTs add up to the Total" in s["checks_run"]
    assert s["checks"] == {"share is not 100 x count / Total": 1}
    review = pd.read_csv(tmp / "ra.review.csv", dtype=str)
    flagged = review[review.failed.notna()]
    # 2 injured of 4,43,366 is a share of 0.0, printed 0.1
    assert flagged[["measure", "name", "column", "value"]].values.tolist() == [
        ["injured", "Lakshadweep", "share_2022", "0.1"]
    ]


def test_joined_cell_is_split() -> None:
    """pdftotext's "21.6 39.9" (one x) fills two columns; nothing after it shifts."""
    head = [(10.0 * (i + 1), str(i + 1)) for i in range(18)]
    full = [(5.0, "1"), (15.0, "Goa")] + [(30.0 + 10 * i, f"{i}.5") for i in range(16)]
    joined = [(5.0, "2"), (15.0, "Assam")]
    joined += [(30.0 + 10 * i, f"{i}.5") for i in range(10)] + [(135.0, "10.5 11.5")]
    joined += [(30.0 + 10 * i, f"{i}.5") for i in range(12, 16)]
    total = [(15.0, "Total")] + [(30.0 + 10 * i, "1") for i in range(16)]
    cells = list(parse([(1, [head, full, joined, total])]))
    got = {c["column"]: c["value"] for c in cells if c["name"] == "Assam"}
    assert got == {col: f"{i}.5" for i, col in enumerate(COLUMNS)}


def test_rank_check() -> None:
    """A rank that is not the 2022 count's place fails."""
    rows = [("a", "300", "1"), ("b", "200", "3"), ("c", "100", "3")]
    df = pd.DataFrame(
        [{"table": 1, "state": s, "column": c, "value": v}
         for s, n, r in rows for c, v in (("2022", n), ("rank_2022", r))]
    )  # fmt: skip
    assert df[rank(df)].state.tolist() == ["b"]
