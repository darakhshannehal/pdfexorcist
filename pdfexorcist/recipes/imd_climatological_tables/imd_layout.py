"""Shared parser for IMD "Climatological Tables of Observatories in India" station pages.

Each station fills two facing pages from one fixed template per edition:
  left  (temperature, humidity, cloud, rain, wind speed): 22 columns
  right (weather phenomena, wind, cloud days, visibility): 35 columns
Rows come in pairs: "I" (03 UTC) and "II" (12 UTC), Jan..Dec, annual (month 13), and in some
editions a "NUMBER OF YEARS" pair (month 14).
Values sit at fixed template x positions. Each engine reports x in its own units (points with
an offset, or pdftotext character columns whose scale varies by page), so every (engine, page)
gets its own column centres: from complete rows, else from the printed header labels, else a
fitted scale.
"""

import re
import statistics
from collections.abc import Iterator
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from pdfexorcist import check
from pdfexorcist.cells import token_boxes
from pdfexorcist.rows import is_value

Template = list[tuple[str, float]]  # (column, template x in pdfplumber points)

LEFT_COLS = [
    "stn_level_pressure_hpa",
    "dry_bulb_c",
    "wet_bulb_c",
    "daily_max_c",
    "daily_min_c",
    "highest_in_month_c",
    "lowest_in_month_c",
    "highest_c",
    "highest_date",
    "lowest_c",
    "lowest_date",
    "rh_pct",
    "vapour_pressure_hpa",
    "all_clouds_okta",
    "low_clouds_okta",
    "rain_monthly_total_mm",
    "rainy_days",
    "rain_wettest_month_mm",
    "rain_driest_month_mm",
    "rain_heaviest_24h_mm",
    "rain_heaviest_date",
    "wind_speed_kmph",
]
RIGHT_COLS = [
    "days_ppt_ge_0_3mm",
    "days_hail",
    "days_thunder",
    "days_fog",
    "days_dust_storm",
    "days_squall",
    "days_wind_ge_62kmph",
    "days_wind_20_61kmph",
    "days_wind_1_19kmph",
    "days_wind_calm",
    "pct_wind_n",
    "pct_wind_ne",
    "pct_wind_e",
    "pct_wind_se",
    "pct_wind_s",
    "pct_wind_sw",
    "pct_wind_w",
    "pct_wind_nw",
    "pct_wind_calm",
    "days_all_cloud_0",
    "days_all_cloud_1_2",
    "days_all_cloud_3_5",
    "days_all_cloud_6_7",
    "days_all_cloud_8",
    "days_low_cloud_0",
    "days_low_cloud_1_2",
    "days_low_cloud_3_5",
    "days_low_cloud_6_7",
    "days_low_cloud_8",
    "days_low_cloud_8_fog",
    "days_vis_lt_1km",
    "days_vis_1_4km",
    "days_vis_4_10km",
    "days_vis_10_20km",
    "days_vis_gt_20km",
]
MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
KEY = ["page", "table", "month", "obs", "col"]
TOL = 0.45  # a token may sit this fraction of the gap to its nearer neighbour column

STATION = re.compile(r"STATION\s*:\s*(.+?)\s*(?:LAT\.|UT\s*:|STATE\s*:|$)")
STATE = re.compile(r"(?:UT|STATE)\s*:\s*(.+?)\s*(?:INDEX|$)")
DEG = re.compile(r"(\d{1,2})\s*°\s*(\d{1,2})\s*'")
PERIOD = re.compile(r"\b(\d{4})\s*-\s*(\d{4})\b")


@dataclass(frozen=True)
class Side:
    """One page of an edition's template."""

    template: Template
    headers: tuple[Template, ...]  # labels printed over columns, one per header line, in order
    marker: float  # template x of the I / II row marker
    title: str  # text found only on this page


@dataclass(frozen=True)
class Layout:
    """One edition's page template."""

    left: Side
    right: Side
    header_alias: dict[str, str] = field(default_factory=dict)  # e.g. "OC" -> "°C"


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def text(line: list) -> str:
    return "  ".join(c[1] for c in line)


def tokens(line: list) -> list[tuple[float, str]]:
    """Whitespace tokens with x (box centre when the engine gives boxes)."""
    return [((b[0] + b[2]) / 2 if b else x, t) for x, t, b in token_boxes(line)]


def cell(page: int, table: str, month: int, obs: str, col: str, value: str) -> dict:
    return {"page": page, "table": table, "month": month, "obs": obs, "col": col, "value": value}


def _marker(toks: list[tuple[float, str]]) -> tuple[str, float, list[str]] | None:
    """The I / II marker and the label words before it, if the row is a data row.

    Vertically lettered headers ("D A I L Y") put a lone "I" after other single letters.
    """
    for i, (x, t) in enumerate(toks):
        if t in ("I", "II"):
            ok = i + 1 == len(toks) or is_value(toks[i + 1][1])
            return (t, x, [w for _, w in toks[:i]]) if ok else None
        if is_value(t) or re.fullmatch(r"[A-Z]", t):
            return None
    return None


def _months(marked: list) -> Iterator[tuple[int, str, list]]:
    """(month, obs, values) per data row.

    Months come from the II rows' printed names (unnamed: 13, then 14), not row counts, which a
    blank row would shift. An I row takes the month of the II row after it.
    """
    pending = None
    prev = 0
    for obs, _, labels, vals in marked:
        if obs == "I":
            pending = vals
            continue
        month = next(
            (MONTHS.index(w) + 1 for w in labels if w in MONTHS), {12: 13, 13: 14}.get(prev, 0)
        )
        if month:
            yield month, "II", vals
            if pending:
                yield month, "I", pending
            prev = month
        pending = None


def _fit_scale(rows: list, template: Template, marker: float) -> float:
    """Scale a in x = xm + a * (T - marker) that best fits the page's value tokens.

    Cost: capped distance to the nearest column, plus the cap per token sharing a column in its row.
    """
    xm = np.array([r_xm for r_xm, vals in rows for _ in vals])
    x = np.array([x for _, vals in rows for x, _ in vals])
    row = np.array([i for i, (_, vals) in enumerate(rows) for _ in vals])
    a = np.arange(0.15, 1.6, 0.002)[:, None]
    t = np.array([t - marker for _, t in template])  # ascending
    u = (x - xm)[None, :] / a  # each token in template units, per scale
    j = np.clip(np.searchsorted(t, u), 1, len(t) - 1)
    dl, dr = u - t[j - 1], t[j] - u
    near = np.where(np.abs(dl) <= np.abs(dr), j - 1, j)
    dist = np.abs(u - t[near])
    cost = np.minimum(dist, 15.0).sum(axis=1)
    keys = np.sort(row[None, :] * len(template) + near, axis=1)
    dups = (np.diff(keys, axis=1) == 0).sum(axis=1)
    return float(a[(cost + 15.0 * dups).argmin(), 0])


def _header_anchors(
    lines: list, header: Template, alias: dict[str, str], need: int = 8
) -> list[tuple[float, float]]:
    """(template x, engine x) pairs from the first line matching >= need labels in printed order."""
    for line in lines:
        toks = [(x, alias.get(t, t)) for x, t in tokens(line)]
        if not toks or header[0][0] not in (t for _, t in toks):
            continue
        out, j = [], 0
        for x, t in toks:
            if j < len(header) and t == header[j][0]:
                out.append((header[j][1], x))
                j += 1
        if len(out) >= need:
            return out
    return []


def _centres(rows: list, lines: list, side: Side, alias: dict) -> list[float]:
    """Column centres for one engine's page, best source first.

    1. Rows holding every column: median x per column.
    2. The header row's labels, interpolated between (absorbs pdftotext's uneven grid).
    3. A linear map fitted to the value tokens, anchored at the I/II marker.
    """
    template, headers, marker = side.template, side.headers, side.marker
    full = [vals for _, vals in rows if len(vals) == len(template)]
    if full:
        return [statistics.median(v[j][0] for v in full) for j in range(len(template))]
    ts = np.array([t for _, t in template], dtype=float)
    anc = _header_anchors(lines, headers[0], alias)
    if anc:
        for extra in headers[1:]:
            anc += _header_anchors(lines, extra, alias, need=len(extra) - 1)
        anc = sorted(dict(anc).items())  # one engine x per template x, left to right
        at, ax = np.array(anc, dtype=float).T
        xs = np.interp(ts, at, ax)
        lo, hi = ts < at[0], ts > at[-1]  # extrapolate with the end segments' slopes
        xs[lo] = ax[0] + (ts[lo] - at[0]) * (ax[1] - ax[0]) / (at[1] - at[0])
        xs[hi] = ax[-1] + (ts[hi] - at[-1]) * (ax[-1] - ax[-2]) / (at[-1] - at[-2])
        return xs.tolist()
    xm = statistics.median(x for x, _ in rows)
    a = _fit_scale(rows, template, marker)
    return (xm + a * (ts - marker)).tolist()


def _place(vals: list, centres: list[float], template: Template) -> dict[str, str]:
    """Assign each value token to its nearest column; join tokens sharing one."""
    out: dict[str, list[str]] = {}
    for x, tok in vals:
        j = min(range(len(centres)), key=lambda k: abs(centres[k] - x))
        lo = centres[j] - centres[j - 1] if j else centres[1] - centres[0]
        hi = centres[j + 1] - centres[j] if j + 1 < len(centres) else lo
        if abs(centres[j] - x) <= TOL * min(lo, hi):
            out.setdefault(template[j][0], []).append(tok)
    return {k: " ".join(v) for k, v in out.items()}


def _left_meta(page_no: int, prev: str) -> Iterator[dict]:
    """Coordinates, height and period from the line above a left page's station name."""
    degs = DEG.findall(prev)
    if len(degs) >= 2:
        yield cell(page_no, "meta", 0, "", "lat", f"{degs[0][0]}°{degs[0][1]}'")
        yield cell(page_no, "meta", 0, "", "lon", f"{degs[1][0]}°{degs[1][1]}'")
        tail = re.sub(r"^[\s'NE]+", "", prev[prev.rfind("'") + 1 :])
        h = re.search(r"(-?\d+(?:\.\d+)?\*?)", PERIOD.sub("", tail))
        if h:
            yield cell(page_no, "meta", 0, "", "height_m", h.group(1))
    p = PERIOD.search(prev)
    if p:
        yield cell(page_no, "meta", 0, "", "period", f"{p.group(1)}-{p.group(2)}")


def _meta(page_no: int, lines: list, table: str) -> Iterator[dict]:
    """Station header fields, voted like any other cell."""
    for i, line in enumerate(lines):
        t = text(line)
        m = STATION.search(t)
        if m:
            yield cell(page_no, "meta", 0, "", "station", norm(m.group(1)))
            if table == "left" and i:
                yield from _left_meta(page_no, text(lines[i - 1]))
        s = STATE.search(t)
        if s and table == "right":
            yield cell(page_no, "meta", 0, "", "state", norm(s.group(1)))


def page_table(lines: list, layout: Layout) -> str | None:
    """'left', 'right' or None for a page. Spacing is ignored: camelot letter-spaces titles."""
    t = re.sub(r"\s+", "", "".join(text(line) for line in lines))
    for table in ("left", "right"):
        if re.sub(r"\s+", "", getattr(layout, table).title) in t:
            return table
    return None


def parse_station_page(page_no: int, lines: list, table: str, layout: Layout) -> Iterator[dict]:
    """Every value on one station page, keyed by KEY."""
    yield from _meta(page_no, lines, table)
    marked = []  # (obs, marker x, label words, [(x, value)]) in printed order
    for line in lines:
        toks = tokens(line)
        mk = _marker(toks)
        if mk is not None:
            marked.append((*mk, [(x, t) for x, t in toks if x > mk[1] and is_value(t)]))
    rows = [(x, vals) for _, x, _, vals in marked if vals]
    if not rows:
        return
    side = getattr(layout, table)
    centres = _centres(rows, lines, side, layout.header_alias)
    for month, obs, vals in _months(marked):
        for col, v in _place(vals, centres, side.template).items():
            yield cell(page_no, table, month, obs, col, v)


def _num(df: pd.DataFrame) -> pd.Series:
    return pd.to_numeric(df.value.str.rstrip("@*#$Š"), errors="coerce")


@check("annual rainfall = sum of monthly (within 1 mm)")
def rain_total(df: pd.DataFrame) -> pd.Series:
    """Fail every monthly-total cell of a station whose annual total disagrees with the sum."""
    sel = (df.col == "rain_monthly_total_mm") & (df.obs == "I")
    w = df[sel].assign(v=_num(df[sel]))
    bad = set()
    for page, g in w.groupby("page"):
        months = g[g.month <= 12].v
        annual = g[g.month == 13].v
        if len(months) == 12 and len(annual) == 1 and abs(months.sum() - annual.iloc[0]) > 1.0:
            bad.add(page)
    return sel & df.page.isin(bad)


@check("wind direction % sums to 100 (within 4)")
def wind_pct(df: pd.DataFrame) -> pd.Series:
    """Fail the direction cells of a row whose percentages are far from 100."""
    sel = df.col.str.startswith("pct_wind_") & (df.month <= 13)
    w = df[sel].assign(v=_num(df[sel]))
    sums = w.groupby(["page", "month", "obs"]).v.transform("sum")
    return sel & df.index.isin(w.index[(sums - 100).abs() > 4])
