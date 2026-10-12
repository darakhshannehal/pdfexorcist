"""SRS Statistical Report, Table 1: percent distribution of population by age."""

import re
from collections.abc import Iterable, Iterator

import pandas as pd

from pdfexorcist import check
from pdfexorcist.rows import Page, split_values

RESIDENCE = ("total", "rural", "urban")
SEX = ("total", "males", "females")
COLS = [f"{r}_{s}" for r in RESIDENCE for s in SEX]
KEY = ["page", "block", "age", "col"]
AGE = re.compile(r"^\d{1,2}-\d{1,2}$|^85\+$|^Total$")
HEADINGS = {"Age", "group", "Table 1", "Total Rural Urban", "Total Males Females"}
STATE = re.compile(r"^[A-Z][A-Za-z&. ]+$")


def parse(pages: Iterable[Page]) -> Iterator[dict]:
    """Yield the nine values of each age row, keyed by its State block on the page.

    A block starts at its 0-4 row; the State heading is an extra column, as camelot may drop it.
    """
    for page_no, lines in pages:
        block, state = 0, ""
        for cells in lines:
            label, vals = split_values(cells)
            label = " ".join(label.split())
            if not vals:
                if STATE.match(label) and not any(h in label for h in HEADINGS):
                    state = label
                continue
            if not AGE.match(label) or len(vals) != len(COLS):
                continue
            if label == "0-4":
                block += 1
            for col, v in zip(COLS, vals, strict=True):
                yield {
                    "page": page_no,
                    "block": block,
                    "age": label,
                    "col": col,
                    "state": state,
                    "value": v,
                }


@check("total lies outside its two parts")
def total_between_parts(df: pd.DataFrame) -> pd.Series:
    """Flag a Total outside its Males/Females or Rural/Urban values, 0.1 allowing for rounding."""
    w = df.assign(v=pd.to_numeric(df.value, errors="coerce")).pivot_table(
        index=["page", "block", "age"], columns="col", values="v", aggfunc="first"
    )
    bad = pd.DataFrame(False, index=w.index, columns=w.columns)
    triples = [(f"{r}_total", f"{r}_males", f"{r}_females") for r in RESIDENCE]
    triples += [(f"total_{s}", f"rural_{s}", f"urban_{s}") for s in SEX]
    for total, a, b in triples:
        if not {total, a, b} <= set(w.columns):
            continue
        lo, hi = w[[a, b]].min(axis=1), w[[a, b]].max(axis=1)
        off = (w[total] < lo - 0.1) | (w[total] > hi + 0.1)  # NaN: not flagged
        for c in (total, a, b):
            bad[c] |= off
    hit = bad.stack()
    at = pd.MultiIndex.from_frame(df[KEY]).isin(hit[hit].index)
    return pd.Series(at, index=df.index)
