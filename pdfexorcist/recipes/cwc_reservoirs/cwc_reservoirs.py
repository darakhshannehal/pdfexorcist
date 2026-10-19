"""CWC weekly storage bulletin of important reservoirs."""

import re
from collections.abc import Iterable, Iterator

import pandas as pd

from pdfexorcist import check
from pdfexorcist.rows import Page, label_key

COLS = [
    "sr",
    "frl",
    "level",
    "live_cap",
    "live",
    "date",
    "pct",
    "pct_last_year",
    "pct_avg10",
    "cca",
    "hydel_mw",
]
PCTS = COLS[6:9]
NUM = r"(\d+(?:\.\d+)?)"
BENEFIT = r"(\d+(?:\.\d+)?|[-$#@])"  # irrigated area and hydel power; $ # @ point to a footnote
ROW = re.compile(
    r"^(\*?)(\d{1,3}) (.+?)"
    + rf" {NUM}" * 4
    + r" (\d\d-\d\d-\d{4})"
    + rf" {NUM}" * 3
    + rf" {BENEFIT} {BENEFIT}$"
)
TOTAL = re.compile(rf"^TOTAL FOR \d+ RESERVOIRS {NUM} {NUM}$")
PERCENT = re.compile(rf"^PERCENTAGE {NUM} {NUM} {NUM}$")
HEADER_END = "1 2 4 6 5 7 8 9 10 11 3A 3B"  # the column-number row under the header


def parse(pages: Iterable[Page]) -> Iterator[dict]:
    """Yield values keyed by reservoir, with its region and state."""
    region = state = None
    for page_no, lines in pages:
        in_table = False
        for cells in lines:
            text = " ".join(t for _, s in cells for t in s.split())
            if not in_table:
                in_table = text == HEADER_END
                continue
            if m := ROW.match(text):
                star, sr, name, *vals = m.groups()
                extra = {"reservoir": name, "region": region, "state": state, "hydel": star}
                yield from _cells(page_no, name, dict(zip(COLS, [sr, *vals], strict=True)), extra)
            elif m := TOTAL.match(text):
                total = dict(zip(["live_cap", "live"], m.groups(), strict=True))
                yield from _cells(page_no, "total", total, {"reservoir": "TOTAL"})
            elif m := PERCENT.match(text):
                pcts = dict(zip(PCTS, m.groups(), strict=True))
                yield from _cells(page_no, "total", pcts, {"reservoir": "TOTAL"})
                return
            elif text and not any(c.isdigit() for c in text):
                if text.endswith("REGION"):
                    region, state = text.removesuffix("REGION").strip(), None
                else:
                    state = text


def _cells(page_no: int, name: str, vals: dict[str, str], extra: dict) -> Iterator[dict]:
    for col, v in vals.items():
        yield {"page": page_no, "id": label_key(name), "col": col, "value": v, **extra}


@check("pct = round(100 * live / live_cap)")
def pct_of_live(df: pd.DataFrame) -> pd.Series:
    """Check this year's storage % against storage and capacity, to the nearest 1."""
    v = pd.to_numeric(df.value, errors="coerce")
    w = df.assign(v=v).pivot_table(index="id", columns="col", values="v", aggfunc="first")
    if not {"pct", "live", "live_cap"} <= set(w.columns):
        return pd.Series(False, index=df.index)
    off = (w.pct - 100 * w.live / w.live_cap).abs() > 0.5 + 1e-9
    bad = {(i, c) for i in off[off].index for c in ("pct", "live", "live_cap")}
    return pd.Series([k in bad for k in zip(df.id, df.col, strict=True)], index=df.index)
