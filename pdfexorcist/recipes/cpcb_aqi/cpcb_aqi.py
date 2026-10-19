"""CPCB daily AQI bulletin."""

import re
from collections.abc import Iterable, Iterator
from datetime import datetime

import pandas as pd

from pdfexorcist import check
from pdfexorcist.rows import Page, label_key

COLS = ["sr", "category", "aqi", "pollutant", "participated", "stations"]
CAT = r"(Good|Satisfactory|Moderate|Very Poor|Poor|Severe)"
ROW = re.compile(rf"^(\d{{1,3}}) (.+?) {CAT} (\d{{1,3}}) (.+) (\d+)/(\d+)$")
SHORT = re.compile(r"^(\d{1,3}) (\d{1,3}) (\d+)/(\d+)$")  # a row whose city wraps
ABOVE = re.compile(rf"^(.+?) {CAT} (.+)$")  # its city, category and pollutant, a line up
# the title on each page: "Air Quality Index on Oct 18, 2026 @ 4 PM" (the 24 hours before)
WHEN = re.compile(r"Air Quality Index on (\w{3}) (\d{1,2}), (\d{4}) @ (\d{1,2}(?::\d\d)?) ?([AP]M)")
# upper bound of each category, from the bulletin's health statements
BANDS = [
    (50, "Good"),
    (100, "Satisfactory"),
    (200, "Moderate"),
    (300, "Poor"),
    (400, "Very Poor"),
    (500, "Severe"),
]


def _text(cells: list) -> str:
    """One line's text, one space between words."""
    return " ".join(t for _, s in cells for t in s.split())


def _when(m: re.Match) -> tuple[str, str]:
    """The bulletin's date and time, as 2026-10-18 and 16:00."""
    clock = m[4] if ":" in m[4] else f"{m[4]}:00"
    at = datetime.strptime(f"{m[1]} {m[2]} {m[3]} {clock} {m[5]}", "%b %d %Y %I:%M %p")
    return at.strftime("%Y-%m-%d"), at.strftime("%H:%M")


def parse(pages: Iterable[Page]) -> Iterator[dict]:
    """Yield each city's values keyed by its name, with the bulletin's date and time."""
    date = time = None
    for page_no, lines in pages:
        in_table = False
        rows: list[list] = []  # city and values; lines below a wrapped row extend the city
        above: re.Match | None = None
        for cells in lines:
            text = _text(cells)
            if m := WHEN.search(text):
                date, time = _when(m)
            if not in_table:
                in_table = "Total Stations" in text
            elif m := ROW.match(text):
                rows.append([m[2], [m[1], *m.groups()[2:]]])
                above = None
            elif (m := SHORT.match(text)) and above:
                rows.append([above[1], [m[1], above[2], m[2], above[3], m[3], m[4]]])
                above = None
            elif m := ABOVE.match(text):
                above = m
            elif text and rows and not SHORT.match(text):
                rows[-1][0] += f" {text}"
        for city, vals in rows:
            for col, v in zip(COLS, vals, strict=True):
                yield {
                    "page": page_no,
                    "id": label_key(city),
                    "col": col,
                    "value": v,
                    "city": city,
                    "date": date,
                    "time": time,
                }


@check("category matches the AQI band")
def category_band(df: pd.DataFrame) -> pd.Series:
    """Flag a category the city's AQI does not fall in."""
    w = df.pivot_table(index=["page", "id"], columns="col", values="value", aggfunc="first")
    if not {"aqi", "category"} <= set(w.columns):
        return pd.Series(False, index=df.index)
    aqi = pd.to_numeric(w.aqi, errors="coerce")
    band = aqi.map(lambda v: next((c for top, c in BANDS if v <= top), None))
    off = band != w.category
    bad = {(p, i, c) for p, i in off[off].index for c in ("aqi", "category")}
    return pd.Series([k in bad for k in zip(df.page, df.id, df.col, strict=True)], index=df.index)
