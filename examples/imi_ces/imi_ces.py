"""IMI Coverage Evaluation Survey 2018, Annexure A: coverage by district."""

from collections import Counter
from collections.abc import Iterable, Iterator

import pandas as pd

from pdfexorcist import check
from pdfexorcist.rows import Page, label_key, split_values

COLUMNS = [
    "fic_nfhs4",
    "fic_ces",
    "no_immunization",
    "fic_urban",
    "fic_rural",
    "bcg",
    "opv3",
    "penta3_dpt3",
    "mcv1",
    "dropout_bcg_mcv1",
    "dropout_penta1_penta3",
]
KEY = ["page", "row", "column"]


def parse(pages: Iterable[Page]) -> Iterator[dict]:
    """Yield the 11 values of each district row.

    A wrapped name leaves the values' line unlabelled; it takes the label lines either side.
    """
    for page_no, lines in pages:
        rows = [split_values(cells) for cells in lines]
        seen: Counter = Counter()
        for i, (label, vals) in enumerate(rows):
            if len(vals) != len(COLUMNS):
                continue
            if not label:
                above = rows[i - 1][0] if i and not rows[i - 1][1] else ""
                below = rows[i + 1][0] if i + 1 < len(rows) and not rows[i + 1][1] else ""
                label = f"{above} {below}".strip()
            key = label_key(label)
            seen[key] += 1
            row = f"{key}#{seen[key]}"
            for col, v in zip(COLUMNS, vals, strict=True):
                yield {"page": page_no, "row": row, "district": label, "column": col, "value": v}


@check("drop-out BCG to MCV-1 is not (BCG - MCV-1) / BCG")
def dropout(df: pd.DataFrame) -> pd.Series:
    """Flag the three cells of a row whose printed drop-out is off by more than rounding."""
    num = df.assign(value=pd.to_numeric(df.value, errors="coerce"))
    w = num.pivot_table(index=["page", "row"], columns="column", values="value", aggfunc="first")
    need = {"bcg", "mcv1", "dropout_bcg_mcv1"}
    if not need <= set(w.columns):
        return pd.Series(False, index=df.index)
    off = ((w.bcg - w.mcv1) / w.bcg * 100 - w.dropout_bcg_mcv1).abs() > 0.2  # NaN: not flagged
    rows = pd.MultiIndex.from_frame(df[["page", "row"]]).isin(off[off].index)
    return pd.Series(rows, index=df.index) & df.column.isin(need)
