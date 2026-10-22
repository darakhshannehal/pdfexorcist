import json
from pathlib import Path

import pandas as pd
from cli_helpers import run

from pdfexorcist.charts import _nice_axis, read_charts

FIXTURES = Path(__file__).parent / "fixtures" / "ncvbdc"
PDF = FIXTURES / "malaria_2026_08_p3_p4_p17.pdf"
CAT3 = FIXTURES / "malaria_2026_08_cat3_charts.pdf"
# "The TPR is ... up to August, 2026" under each TPR chart of the Category III report
CAT3_TPR = {"CATEGORY III": 0.62, "MIZORAM": 3.44, "ODISHA": 0.54, "TRIPURA": 0.63}


def _tidy(df: pd.DataFrame) -> pd.DataFrame:
    """kind (Tested, TPR ...), which (Current Year ...) and area, from series and title."""
    return df.assign(
        kind=df.series.str.split().str[0],
        which=df.series.str.split(n=1).str[1],
        area=df.title.str.extract(r" IN (.+?)(?: STATES/UTs)?$")[0],
    )


def _tpr_check(df: pd.DataFrame) -> pd.Series:
    """Per point, whether the TPR chart equals Positive / Tested * 100 within the pm's.

    Not for "Avg Last 3 Years": its TPR is a mean of ratios.
    """
    df = _tidy(df[~df.series.str.endswith("Avg Last 3 Years")])
    key = ["area", "which", "category"]
    v = df.pivot_table(index=key, columns="kind", values="value")
    pm = df.pivot_table(index=key, columns="kind", values="pm")
    tpr = v.Positive / v.Tested * 100
    return (v.TPR - tpr).abs() <= tpr * (pm.Positive / v.Positive + pm.Tested / v.Tested) + pm.TPR


def test_series_and_titles() -> None:
    df = read_charts(PDF, [1, 2])
    g1 = df[(df.page == 1) & (df.chart == 1)]
    assert g1.title.iloc[0] == "GRAPH 1: MONTH WISE TREND OF TESTED IN INDIA"
    assert g1.groupby("series").size().to_dict() == {
        "Tested Current Year": 8,  # the report month is August
        "Tested Last Year": 12,
        "Tested Avg Last 3 Years": 12,
    }
    assert set(df.status) == {"estimated"}


def test_tpr_chart_agrees_with_tested_and_positive_charts() -> None:
    df = read_charts(PDF, [1, 2])
    ok = _tpr_check(df)
    assert len(ok) == 20 and ok.all()
    cur = _tidy(df).query("which == 'Current Year'").groupby("kind").value.sum()
    assert round(cur.Positive / cur.Tested * 100, 2) == 0.12  # "The TPR is 0.12"


def test_category_iii_report() -> None:
    """Every chart reads; the TPR charts agree with the Positive and Tested charts."""
    df = read_charts(CAT3)
    assert not df.attrs["skipped"]
    assert df.groupby(["page", "chart"]).ngroups == 16
    assert set(_tidy(df).area) == set(CAT3_TPR)
    ok = _tpr_check(df)
    assert len(ok) == 4 * 20 and ok.all()


def test_category_iii_cumulative_tpr_matches_the_text() -> None:
    """Positive / Tested * 100 to date, within its pm bound plus the text's rounding."""
    cur = _tidy(read_charts(CAT3)).query("which == 'Current Year'")
    for area, stated in CAT3_TPR.items():
        sums = cur[cur.area == area].groupby("kind")[["value", "pm"]].sum()
        p, t = sums.loc["Positive"], sums.loc["Tested"]
        tpr = p.value / t.value * 100
        bound = tpr * (p.pm / p.value + t.pm / t.value) + 0.005
        assert abs(tpr - stated) <= bound, (area, tpr, stated)


def test_rounded_tick_labels() -> None:
    """Category O's Positive ticks read 0 0 0 0 0 1 1 1 1 1; the text says no case."""
    df = read_charts(PDF, [3])
    pos = df[df.chart == 2]
    assert len(pos) == 32 and not df.attrs["skipped"]
    assert (pos.value.abs() <= pos.pm).all()


def test_nice_axis() -> None:
    ys = [100.0 - 10 * i for i in range(10)]
    nice = _nice_axis(ys, [0, 0, 0, 0, 0, 1, 1, 1, 1, 1], 0)
    assert nice is not None
    a, b = nice
    assert (round(a + b * ys[0], 9), round(a + b * ys[-1], 9)) == (0, 0.9)
    assert _nice_axis(ys[:6], [0, 1, 1, 2, 2, 3], 0) is not None  # 0 ... 2.5 by 0.5
    assert _nice_axis(ys[:4], [0, 0, 1, 7], 0) is None


def test_cli(tmp_path: Path) -> None:
    out = tmp_path / "c.csv"
    r = run(["charts", str(PDF), "-p", "1", "-o", str(out)])
    assert r.exit_code == 0, r.output
    assert len(out.read_text().splitlines()) == 1 + 2 * 32


def test_cli_json(tmp_path: Path) -> None:
    """The summary the web page reads (web/core.js charts)."""
    out = tmp_path / "c.csv"
    r = run(["charts", str(PDF), "-p", "3-", "-o", str(out), "--json"])
    assert r.exit_code == 0, r.output
    summary = json.loads(r.stdout)
    assert summary["outputs"] == [str(out)] and summary["exit_code"] == 0
    assert (summary["points"], summary["charts"], summary["skipped"]) == (64, 2, [])


def test_cli_matches_the_library(tmp_path: Path) -> None:
    """The CSV the CLI and the web page write is read_charts as CSV."""
    out = tmp_path / "c.csv"
    assert run(["charts", str(CAT3), "-o", str(out)]).exit_code == 0
    # read_text turns the file's line ends into "\n"; to_csv gives the platform's
    assert out.read_text() == read_charts(CAT3).to_csv(index=False, lineterminator="\n")


def test_title_in_the_box() -> None:
    """Karnataka IDSP draws Excel's own titles; weekly lines under month labels are skipped."""
    df = read_charts(FIXTURES.parent / "karnataka_idsp" / "karnataka_idsp_2026_week41.pdf", [2])
    assert set(df.title) == {
        "Trend of Malaria reported in the current year",
        "Trend of JE reported in the current year",
    }
    reasons = {why.split(" at ")[0] for _, _, why in df.attrs["skipped"]}  # weekly points
    assert reasons == {"series '#ed7d31' has two points", "a point"}
