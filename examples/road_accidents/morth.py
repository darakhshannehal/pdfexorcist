"""MoRTH Road Accidents in India 2022, Annexures 2-4: accidents, killed and injured by State/UT."""

import re
import statistics
from collections.abc import Iterable, Iterator
from itertools import groupby, pairwise

import pandas as pd

from pdfexorcist import check
from pdfexorcist.cells import token_boxes
from pdfexorcist.rows import Page, is_value, label_key

YEARS = ["2019", "2020", "2021", "2022"]
COLUMNS = [
    *YEARS,
    "rank_2022",
    *(f"share_{y}" for y in YEARS),
    *(f"per_lakh_pop_{y}" for y in YEARS),
    "per_10k_vehicles_2019",
    "per_10k_vehicles_2020",
    "per_10k_km_roads_2019",
]
KEY = ["table", "state", "column"]
TITLE = re.compile(r"Total Number of (Road Accidents|Persons Killed|Persons Injured) in")
MEASURE = {"Road Accidents": "accidents", "Persons Killed": "killed", "Persons Injured": "injured"}
HEADER = [str(i) for i in range(1, 19)]  # the printed column numbers, 1 to 18
PLACEHOLDERS = {"#", "$"}  # population not available; Daman & Diu merged in 2020


def _cells(line: list) -> tuple[str, list[tuple[float, str]]]:
    """A data line's state name and its positioned values, the serial number dropped."""
    toks = [(x, t) for x, t, _ in token_boxes(line)]
    if len(toks) > 1 and toks[0][1].isdigit() and not is_value(toks[1][1]):
        toks = toks[1:]
    vals = [(x, t) for x, t in toks if is_value(t) or t in PLACEHOLDERS]
    label = [t for _, t in toks if not (is_value(t) or t in PLACEHOLDERS)]
    return " ".join(label), vals


def _table(rows: list[tuple[str, list[tuple[float, str]]]]) -> Iterator[tuple[str, str, str]]:
    """(state, column, value) of one table, each value placed at its nearest column.

    A pdftotext cell holding two values ("21.6 39.9") sets no column centres.
    """
    n = len(COLUMNS)
    full = [v for _, v in rows if len(v) == n and all(a[0] < b[0] for a, b in pairwise(v))]
    if not full:
        return
    centres = [statistics.median(v[i][0] for v in full) for i in range(n)]
    for state, vals in rows:
        last = -1
        for x, cell in groupby(vals, key=lambda v: v[0]):
            toks = [t for _, t in cell]
            k = len(toks)
            start = min(range(n - k + 1), key=lambda c: abs(sum(centres[c : c + k]) / k - x))
            start = max(start, last + 1)
            for col, t in zip(range(start, n), toks, strict=False):
                yield state, COLUMNS[col], t
            last = start + k - 1


def parse(pages: Iterable[Page]) -> Iterator[dict]:
    """Yield every value of each State/UT table, keyed by table, state and column, commas dropped.

    A table read twice (camelot reads the off-page neighbour) is yielded once. The
    measure is an extra column; camelot drops the title it comes from.
    """
    seen: set[tuple] = set()
    measure, rows, inside = None, [], False
    for _, lines in pages:
        for line in lines:
            text = " ".join(t for _, t in line)
            if m := TITLE.search(text):
                measure = MEASURE[m.group(1)]
            elif text.split() == HEADER:
                rows, inside = [], True
            elif inside:
                state, vals = _cells(line)
                if not vals:
                    continue
                rows.append((state, vals))
                if state != "Total":
                    continue
                inside = False
                sig = tuple((s, tuple(t for _, t in v)) for s, v in rows)
                if sig in seen:
                    continue
                seen.add(sig)
                for state, col, value in _table(rows):
                    yield {
                        "table": len(seen),
                        "state": label_key(state),
                        "column": col,
                        "value": value,
                        "name": state,
                        "measure": measure,
                    }
                measure = None


def _wide(df: pd.DataFrame) -> pd.DataFrame:
    """Numbers by (table, state) and column."""
    num = df.assign(v=pd.to_numeric(df.value, errors="coerce"))
    return num.pivot_table(index=["table", "state"], columns="column", values="v", aggfunc="first")


def _flag(df: pd.DataFrame, bad: pd.DataFrame) -> pd.Series:
    """Rows of df whose (table, state, column) is True in the wide frame bad."""
    hits = bad.stack()
    hits = hits[hits.astype(bool)]
    idx = pd.MultiIndex.from_frame(df[KEY])
    return pd.Series(idx.isin(hits.index), index=df.index)


@check("share is not 100 x count / Total")
def share(df: pd.DataFrame) -> pd.Series:
    """Flag a share that is off its count's share of the Total by more than rounding."""
    w = _wide(df)
    bad = pd.DataFrame(False, index=w.index, columns=w.columns)
    has_total = "total" in w.index.get_level_values("state")
    for y in YEARS:
        if has_total and {y, f"share_{y}"} <= set(w.columns):
            total = w[y].xs("total", level="state").reindex(w.index, level="table")
            bad[f"share_{y}"] = (100 * w[y] / total - w[f"share_{y}"]).abs() > 0.051
    return _flag(df, bad)


@check("rank is not the 2022 count's place")
def rank(df: pd.DataFrame) -> pd.Series:
    """Flag a 2022 rank that is not 1 + the number of States/UTs with a larger count."""
    w = _wide(df)
    bad = pd.DataFrame(False, index=w.index, columns=w.columns)
    if {"2022", "rank_2022"} <= set(w.columns):
        states = w.drop("total", level="state", errors="ignore")["2022"]
        place = states.groupby(level="table").rank(method="min", ascending=False)
        bad["rank_2022"] = (place - w["rank_2022"]).reindex(w.index).abs() > 0
    return _flag(df, bad)
