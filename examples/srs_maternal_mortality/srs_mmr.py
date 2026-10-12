"""SRS Special Bulletin on Maternal Mortality: MMR by State and deaths by age.

An interval "(79,96)" becomes <column>_lower and <column>_upper; a percent drops its "%"
and its column ends in _pct.
"""

import re
from collections import Counter
from collections.abc import Iterable, Iterator

import pandas as pd

from pdfexorcist import check
from pdfexorcist.rows import Cell, Page, label_key

KEY = ["page", "row", "column"]
STATE = ["mmr", "mmr_lower", "mmr_upper", "mortality_rate", "lifetime_risk_pct"]
AGE = [
    "maternal_pct",
    "maternal_lower",
    "maternal_upper",
    "non_maternal_pct",
    "non_maternal_lower",
    "non_maternal_upper",
]
NUM = re.compile(r"^\d+(\.\d+)?%?$")
CI = re.compile(r"^\((\d+),(\d+)\)$")


def tokens(cells: list[Cell]) -> list[str]:
    """Split a line into tokens, mending PDFium's "0.18 %", "(18,26 )" and "30 - 34"."""
    text = " ".join(t for _, t in cells)
    text = re.sub(r"\s+(?=[%)])", "", text)
    text = re.sub(r"(?<=\d)\s*-\s*(?=\d)", "-", text)
    return text.split()


def split_line(toks: list[str]) -> tuple[str, list[str]]:
    """Return the label and the trailing numbers and intervals."""
    i = len(toks)
    while i and (NUM.match(toks[i - 1]) or CI.match(toks[i - 1])):
        i -= 1
    return " ".join(toks[:i]), toks[i:]


def row_values(vals: list[str]) -> list[tuple[str, str]] | None:
    """Name the values of a State row (Table 1) or an age row (Table 2), else None."""
    shape = ["%" if v.endswith("%") else "ci" if CI.match(v) else "n" for v in vals]
    if shape == ["n", "ci", "n", "%"]:
        names, flat = STATE, [vals[0], *CI.findall(vals[1])[0], vals[2], vals[3]]
    elif shape == ["%", "ci", "%", "ci"]:
        names = AGE
        flat = [vals[0], *CI.findall(vals[1])[0], vals[2], *CI.findall(vals[3])[0]]
    elif shape == ["%", "%"]:
        names, flat = [AGE[0], AGE[3]], vals
    else:
        return None
    return [(n, v.rstrip("%")) for n, v in zip(names, flat, strict=True)]


def parse(pages: Iterable[Page]) -> Iterator[dict]:
    """Yield one cell per value; "SUBTOTAL" takes the label line above it ("EAG AND ASSAM")."""
    for page_no, lines in pages:
        seen: Counter = Counter()
        prev = ""
        for cells in lines:
            label, vals = split_line(tokens(cells))
            named = row_values(vals) if label else None
            if named is None:
                prev = label if label and not vals else ""
                continue
            if label.upper() == "SUBTOTAL" and prev:
                label = f"{prev} {label}"
            prev = ""
            key = label_key(label)
            seen[key] += 1
            row = f"{key}#{seen[key]}"
            for col, v in named:
                yield {"page": page_no, "row": row, "area": label, "column": col, "value": v}


def _wide(df: pd.DataFrame) -> pd.DataFrame:
    """One row per (page, row), one numeric column per value."""
    num = df.assign(value=pd.to_numeric(df.value, errors="coerce"))
    return num.pivot_table(index=["page", "row"], columns="column", values="value", aggfunc="first")


def _flag(df: pd.DataFrame, bad: pd.Series, cols: set[str]) -> pd.Series:
    """Mark the cells in cols of the (page, row) pairs where bad is True."""
    rows = pd.MultiIndex.from_frame(df[["page", "row"]]).isin(bad[bad].index)
    return pd.Series(rows, index=df.index) & df.column.isin(cols)


@check("estimate outside its 95% CI")
def within_ci(df: pd.DataFrame) -> pd.Series:
    """Flag an MMR or proportion that falls outside its own printed interval."""
    w = _wide(df)
    out = pd.Series(False, index=df.index)
    for est in ("mmr", "maternal_pct", "non_maternal_pct"):
        prefix = est.removesuffix("_pct")
        lo, hi = f"{prefix}_lower", f"{prefix}_upper"
        if not {est, lo, hi} <= set(w.columns):
            continue
        bad = (w[est] < w[lo]) | (w[est] > w[hi])  # NaN: not flagged
        out |= _flag(df, bad, {est, lo, hi})
    return out


@check("lifetime risk is not 1 - (1 - rate/100000)^35")
def lifetime_risk(df: pd.DataFrame) -> pd.Series:
    """Flag a lifetime risk outside the bulletin's formula, given the rate is rounded to 1."""
    w = _wide(df)
    if not {"mortality_rate", "lifetime_risk_pct"} <= set(w.columns):
        return pd.Series(False, index=df.index)

    def risk(rate: pd.Series) -> pd.Series:
        return 100 * (1 - (1 - rate / 100000) ** 35)

    lo = risk(w.mortality_rate - 0.5) - 0.005
    hi = risk(w.mortality_rate + 0.5) + 0.005
    bad = (w.lifetime_risk_pct < lo) | (w.lifetime_risk_pct > hi)
    return _flag(df, bad, {"mortality_rate", "lifetime_risk_pct"})
