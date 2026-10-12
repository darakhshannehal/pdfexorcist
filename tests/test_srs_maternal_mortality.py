"""SRS Special Bulletin on Maternal Mortality 2021-23: intervals and percents."""

import json
import shutil
from pathlib import Path

import pandas as pd
import pytest
import srs_cod_top10 as cod
from cli_helpers import run
from srs_mmr import AGE, KEY, STATE, lifetime_risk, parse, within_ci

from pdfexorcist import extract

ROOT = Path(__file__).parent.parent
FIXTURES = Path(__file__).parent / "fixtures" / "srs_mmr"
PDF = FIXTURES / "srs_mmr_bulletin_2021-23.pdf"
COD = FIXTURES / "srs_cod_2021-23_p31.pdf"
RECIPE = ROOT / "examples" / "srs_maternal_mortality" / "recipe.toml"


def _expected(name: str) -> pd.DataFrame:
    return pd.read_csv(FIXTURES / name, dtype=str, keep_default_na=False).set_index("area")


@pytest.fixture(scope="module")
def res() -> pd.DataFrame:
    """Both tables of the bulletin, read by the five text engines."""
    return extract(PDF, parse=parse, key=KEY, checks=[within_ci, lifetime_risk])


def test_every_cell_unanimous(res: pd.DataFrame) -> None:
    """All five engines agree on every value, and no check fails."""
    assert (res.status == "verified").all() and (res.n_agree == 5).all()
    assert len(res) == 24 * len(STATE) + 7 * len(AGE) + 2
    assert (res.failed == "").all()


def test_state_table(res: pd.DataFrame) -> None:
    """Pin MMR, CI bounds, rate and lifetime risk of every State and subtotal."""
    got = res[res.page == 3].pivot(index="area", columns="column", values="value")[STATE]
    want = _expected("expected.csv")
    pd.testing.assert_frame_equal(got.sort_index(), want.sort_index(), check_names=False)
    assert got.loc["INDIA"].tolist() == ["88", "79", "96", "5", "0.18"]
    assert "EAG AND ASSAM SUBTOTAL" in got.index  # the label wraps onto two lines


def test_age_table(res: pd.DataFrame) -> None:
    """Pin the age distribution; the 15-49 total has no interval."""
    got = res[res.page == 4].pivot(index="area", columns="column", values="value")
    got = got.reindex(columns=AGE).fillna("")
    want = _expected("expected_age.csv")
    pd.testing.assert_frame_equal(got.sort_index(), want.sort_index(), check_names=False)


def test_checks_catch_a_misread(res: pd.DataFrame) -> None:
    """An MMR outside its CI and a lifetime risk off the formula are flagged."""
    bad = res.copy()
    india = bad.area == "INDIA"
    bad.loc[india & (bad.column == "mmr"), "value"] = "98"
    bad.loc[india & (bad.column == "lifetime_risk_pct"), "value"] = "0.81"
    ci, risk = within_ci(bad), lifetime_risk(bad)
    assert set(bad[ci].column) == {"mmr", "mmr_lower", "mmr_upper"}
    assert set(bad[risk].column) == {"mortality_rate", "lifetime_risk_pct"}
    assert set(bad[ci | risk].area) == {"INDIA"}


@pytest.mark.usefixtures("wide_console")
def test_recipe(tmp_path: Path) -> None:
    """The recipe reads page 3 only and writes the State table."""
    pdf = tmp_path / "mmr.pdf"
    shutil.copy(PDF, pdf)
    r = run(["extract", str(pdf), "--recipe", str(RECIPE), "--json", "-q"])
    s = json.loads(r.stdout)
    assert r.exit_code == 0 and s["cells"]["verified"] == 120 and s["cells"]["unresolved"] == 0
    assert len(s["checks_run"]) == 2
    t = pd.read_csv(tmp_path / "mmr.csv", dtype=str, keep_default_na=False).set_index("area")
    pd.testing.assert_frame_equal(t, _expected("expected.csv"))


def test_cod_top10() -> None:
    """Cause of Death Table 2.3A: every share verified, each sex adds up to 100."""
    res = extract(COD, parse=cod.parse, key=cod.KEY, checks=[cod.adds_to_100])
    assert (res.status == "verified").all() and (res.n_agree == 5).all()
    assert (res.failed == "").all()
    got = res.pivot(index=["rank", "cause"], columns="sex", values="value")[cod.SEXES]
    want = pd.read_csv(FIXTURES / "expected_cod.csv", dtype=str).set_index(["rank", "cause"])
    pd.testing.assert_frame_equal(got.sort_index(), want.sort_index(), check_names=False)
    bad = res.copy()
    bad.loc[(bad["rank"] == "1") & (bad.sex == "male"), "value"] = "23.4"  # printed 32.4
    assert set(bad[cod.adds_to_100(bad)].sex) == {"male"}
