"""IMI Coverage Evaluation Survey 2018, Annexure A: coverage by district."""

from collections import Counter
from collections.abc import Iterable, Iterator

import pandas as pd

from pdfexorcist import check
from pdfexorcist.rows import Cell, Page, label_key, split_values

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


def _label_cells(cells: list[Cell], n_values: int) -> list[str]:
    """Return the text of the cells before a line's n_values trailing values."""
    texts = [text for _, text in cells]
    while n_values and texts:
        n_values -= len(texts.pop().split())
    return texts


def parse(pages: Iterable[Page]) -> Iterator[dict]:
    """Yield the 11 values of each district row.

    State and District are separate cells; the first label cell is the state.
    A wrapped name leaves the values' line unlabelled; it takes the label lines either side.
    """
    for page_no, lines in pages:
        vals_of = [split_values(cells)[1] for cells in lines]
        rows = [(_label_cells(c, len(v)), v) for c, v in zip(lines, vals_of, strict=True)]
        seen: Counter = Counter()
        for i, (names, vals) in enumerate(rows):
            if len(vals) != len(COLUMNS):
                continue
            if not names:
                for j in (i - 1, i + 1):
                    if 0 <= j < len(rows) and not rows[j][1]:
                        names = names + rows[j][0]
            state, rest = (names[0], names[1:]) if len(names) > 1 else ("", names)
            district = " ".join(rest)
            key = label_key(f"{state} {district}")
            seen[key] += 1
            row = f"{key}#{seen[key]}"
            for col, v in zip(COLUMNS, vals, strict=True):
                yield {
                    "page": page_no,
                    "row": row,
                    "state": state,
                    "district": district,
                    "column": col,
                    "value": v,
                }


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
