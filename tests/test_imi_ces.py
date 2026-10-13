"""IMI Coverage Evaluation Survey 2018: a table printed sideways."""

from pathlib import Path

import pandas as pd
from imi_ces import COLUMNS, KEY, dropout, parse

from pdfexorcist import extract

FIXTURES = Path(__file__).parent / "fixtures" / "imi_ces"


def test_sideways_annexure():
    """Every value verified, states split off, wrapped names joined, one misprint flagged."""
    res = extract(
        FIXTURES / "imi_ces_2018_annexure_p38-44.pdf", parse=parse, key=KEY, checks=[dropout]
    )
    ok = res[res.status == "verified"]
    got = ok.pivot(index=["state", "district"], columns="column", values="value")[COLUMNS]
    want = pd.read_csv(FIXTURES / "expected.csv", dtype=str).set_index(["state", "district"])
    pd.testing.assert_frame_equal(got.sort_index(), want.sort_index(), check_names=False)
    flagged = ok[ok.failed != ""]
    # BCG 97.7, MCV-1 97.9, printed 0.0
    assert set(zip(flagged.state, flagged.district, strict=True)) == {("Sikkim", "East District")}
