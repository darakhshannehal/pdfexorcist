"""IMD Climatological Tables of Observatories in India 1961-1990 (6th ed., 2010).

Differences from 1991-2020: a "NUMBER OF YEARS" row pair after the annual row (month 14),
annual records without dates, values flagged "@" / "*", °C printed as a raised O plus C,
Hindi in a legacy font (reads as ASCII gibberish), and an English "List of Observatories"
with coordinates, barometer/anemometer heights and a description of each site.
"""

import re
from collections.abc import Iterable, Iterator

from imd_layout import (
    LEFT_COLS,
    RIGHT_COLS,
    Layout,
    Side,
    cell,
    norm,
    page_table,
    parse_station_page,
    text,
    tokens,
)

from pdfexorcist.rows import Page

LEFT = list(
    zip(
        LEFT_COLS,
        (
            172,
            220,
            254,
            288,
            323,
            364,
            411,
            460,
            502,
            542,
            592,
            644,
            698,
            753,
            802,
            849,
            893,
            937,
            986,
            1036,
            1078,
            1114,
        ),
        strict=True,
    )
)
RIGHT = list(
    zip(
        RIGHT_COLS,
        (
            117,
            156,
            189,
            222,
            255,
            288,
            321,
            354,
            387,
            420,
            450,
            477,
            504,
            531,
            558,
            588,
            615,
            642,
            669,
            699,
            726,
            753,
            780,
            807,
            834,
            861,
            891,
            918,
            945,
            972,
            1005,
            1041,
            1074,
            1110,
            1146,
        ),
        strict=True,
    )
)
LAYOUT = Layout(
    left=Side(
        LEFT,
        # the units row (the okta and km/h units are printed in Hindi only)
        headers=(
            [("hPa", 172)]
            + [("°C", x) for x in (220, 254, 288, 323, 364, 411, 460, 542)]
            + [("%", 644), ("hPa", 698), ("mm", 849), ("mm", 937), ("mm", 986), ("mm", 1036)],
        ),
        marker=135,
        title="HEIGHT ABOVE",
    ),
    right=Side(
        RIGHT,
        headers=(
            [
                ("HAIL", 156),
                ("FOG", 222),
                ("20-61", 354),
                ("0", 420),
                *zip(
                    ("N", "NE", "E", "SE", "S", "SW", "W", "NW", "CALM"),
                    (450, 477, 504, 531, 558, 588, 615, 642, 669),
                    strict=True,
                ),
                *zip(
                    ("0", "T-2", "3-5", "6-7", "8") * 2,
                    (699, 726, 753, 780, 807, 834, 861, 891, 918, 945),
                    strict=True,
                ),
            ],
            # THUN-DER, DUST STORM, SQU-ALL, 1-19, fog 8, visibility units
            [
                ("DER", 189),
                ("STORM", 255),
                ("ALL", 288),
                ("1-19", 387),
                ("8", 972),
                ("Km.", 1005),
                ("Kms.", 1041),
                ("Kms.", 1074),
                ("Kms.", 1110),
            ],
        ),
        marker=89,
        title="WEATHER PHENOMENA",
    ),
    header_alias={"OC": "°C", "C": "°C", "0C": "°C"},
)

# a station's first line in the List of Observatories (dates as printed, incl. "1 909", "N.A."):
#   name  state  page  established  lat  lon  Hp  Ha  description...
START = re.compile(
    r"^(?P<name>\S.*?)\s{2,}(?P<state>\S.*?)\s{2,}(?P<page>\d{1,3})\s+(?P<established>(?:\d{1,2}(?:st|nd|rd|th)?\s*)?(?:[A-Z][a-z]{2,8}[,.]?\s*)?\d\s*\d{3}|N\.A\.)"
    r"\s+(?P<lat>\d{1,2}\s+\d{1,2})\s+(?P<lon>\d{2,3}\s+\d{1,2})\s+(?P<hp_m>\S+)\s+(?P<ha_m>\S+)\s+(?P<description>\S.*)$"
)
INDEX_NO = re.compile(r"^\((\d{4,5})\)$")  # Umaria prints "(4267)"
OBS_CLASS = re.compile(
    r"^[A-Z]\.?[A-Z]?\.?\s?O\.?\s?(\(\w+\))?$|^P\.\s?T\.\s?O\.?$"
)  # also "D.O(I)"


def _stations(page_no: int, lines: list) -> Iterator[dict]:
    """English List of Observatories: one record per station, keyed by index no."""
    rec: dict | None = None
    xs = (0.0, 0.0, 0.0)  # first-line x of the state, page and description columns

    def flush(r: dict | None) -> Iterator[dict]:
        if r and r.get("index_no"):
            for col in (
                "name",
                "state",
                "established",
                "lat",
                "lon",
                "hp_m",
                "ha_m",
                "obs_class",
                "description",
            ):
                if r.get(col):
                    yield cell(page_no, "stations", int(r["index_no"]), "", col, norm(r[col]))
            yield cell(page_no, "stations", int(r["index_no"]), "", "page", r["page"])

    for line in lines:
        joined = re.sub(r"\s{2,}", "  ", text(line)).strip()
        m = START.match(joined)
        if m:
            yield from flush(rec)
            rec = m.groupdict()
            toks = tokens(line)
            first = {w: x for x, w in reversed(toks)}
            xs = (
                first.get(m["state"].split()[0], 0.0),
                first.get(m["page"], 0.0),
                first.get(m["description"].split()[0], 0.0),
            )
            continue
        if rec is None:
            continue
        if joined.startswith("NOTE"):  # page footnotes follow the last record
            yield from flush(rec)
            rec = None
            continue
        for c in line:  # engines split lines into text runs
            x, t = c[0], norm(c[1])
            idx = INDEX_NO.match(t)
            if idx:
                rec["index_no"] = idx.group(1)
            elif OBS_CLASS.match(t):
                rec["obs_class"] = t
            elif x >= xs[2] - 5:
                rec["description"] += " " + t
            elif x >= xs[0] - 5 and x < xs[1]:
                rec["state"] += " " + t
            elif x < xs[0]:
                rec["name"] += " " + t
    yield from flush(rec)


def parse(pages: Iterable[Page]) -> Iterator[dict]:
    """Yield one dict per printed value, keyed by imd_layout.KEY."""
    for page_no, lines in pages:
        table = page_table(lines, LAYOUT)
        if table:
            yield from parse_station_page(page_no, lines, table, LAYOUT)
        elif "Location and environment" in " ".join(text(line) for line in lines):
            yield from _stations(page_no, lines)
