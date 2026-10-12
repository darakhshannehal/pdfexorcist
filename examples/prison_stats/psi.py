"""NCRB Prison Statistics India: capacity, inmates and occupancy by State/UT (Tables 1.2, 1.3)."""

import re
from collections.abc import Iterable, Iterator

import pandas as pd

from pdfexorcist import check
from pdfexorcist.rows import Page, label_key, split_values

HEADER = re.compile(r"^\((\d+)\)$")  # the column-number row: (1) (2) (3) ...
MEASURES = ("capacity", "inmates", "occupancy")
SEXES = ("M", "F", "Tr", "Total")  # Table 1.2: columns (3)-(14)
# Table 1.3: columns (3)-(29), three to a jail type, over three pages
JAILS = ("Central", "District", "Sub", "Women", "Borstal", "Open", "Special", "Other", "Total")


def _metric(table: str, col: int) -> tuple[str, str, str]:
    """Printed column number -> (group, measure, column name)."""
    if table == "1.2":
        measure, group = MEASURES[(col - 3) // 4], SEXES[(col - 3) % 4]
        name = measure if group == "Total" else f"{measure}_{group.lower()}"
    else:
        group, measure = JAILS[(col - 3) // 3], MEASURES[(col - 3) % 3]
        name = f"{'all' if group == 'Total' else group.lower()}_{measure}"
    return group, measure, name


def _header(cells: list) -> list[int] | None:
    """The printed column numbers, if this line is the column-number row."""
    toks = [t for _, text in cells for t in text.split()]
    nums = [int(m.group(1)) for t in toks if (m := HEADER.match(t))]
    return nums if len(nums) >= 3 and len(nums) == len(toks) else None


def parse(pages: Iterable[Page]) -> Iterator[dict]:
    """Yield each State/UT and total row's values, keyed by printed column number."""
    for page_no, lines in pages:
        start, hdr = next(((i, h) for i, c in enumerate(lines) if (h := _header(c))), (0, None))
        if hdr is None:
            continue  # no column-number row seen: this engine abstains
        cols = [c for c in hdr if c >= 3]
        table = "1.2" if cols[-1] == 14 else "1.3"
        metrics = [_metric(table, c) for c in cols]
        section, pending = "state", ""
        for cells in lines[start + 1 :]:
            label, vals = split_values(cells)
            if not vals:
                pending = label  # camelot can put the name on a line of its own
                continue
            if len(vals) != len(cols):
                continue
            name = re.sub(r"^\d+\s*", "", label or pending)
            row = label_key(name)
            is_total = row.startswith("total")
            for col, (group, measure, column), v in zip(cols, metrics, vals, strict=True):
                yield {
                    "page": page_no,
                    "row": row,
                    "col": col,
                    "state": name,
                    "section": "total" if is_total else section,
                    "table": table,
                    "group": group,
                    "measure": measure,
                    "column": column,
                    "value": v,
                }
            if row == "totalstates":
                section = "ut"
            if row == "totalallindia":
                break  # notes under the table


@check("occupancy = 100 x inmates / capacity (to 0.1)")
def occupancy(df: pd.DataFrame) -> pd.Series:
    """Flag the three cells of a group whose printed occupancy rate is off by more than rounding."""
    num = df.assign(v=pd.to_numeric(df.value, errors="coerce"))
    w = num.pivot_table(
        index=["page", "row", "group"], columns="measure", values="v", aggfunc="first"
    )
    if not set(MEASURES) <= set(w.columns):
        return pd.Series(False, index=df.index)
    want = 100 * w.inmates / w.capacity
    off = ((want - w.occupancy).abs() > 0.051) & (w.capacity > 0)  # NaN: not flagged
    at = pd.MultiIndex.from_frame(df[["page", "row", "group"]]).isin(off[off].index)
    return pd.Series(at, index=df.index)
