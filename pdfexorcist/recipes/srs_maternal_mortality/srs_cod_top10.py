"""SRS Cause of Death 2021-23, Table 2.3A: top 10 causes of death in India by sex."""

import re
from collections.abc import Iterable, Iterator

import pandas as pd

from pdfexorcist import check
from pdfexorcist.rows import Page

KEY = ["page", "rank", "sex"]
SEXES = ["male", "female", "person"]
SHARE = re.compile(r"^\d+\.\d$")
OTHER = "All Other Remaining Causes"


def parse(pages: Iterable[Page]) -> Iterator[dict]:
    """Yield the three shares of each ranked cause and of the remainder.

    Keyed by rank, so a cause wrapped onto two lines (camelot joins it) still gets one vote.
    """
    for page_no, lines in pages:
        for cells in lines:
            toks = " ".join(t for _, t in cells).split()
            if len(toks) < 5 or not all(SHARE.match(t) for t in toks[-3:]):
                continue
            label = " ".join(toks[:-3])
            if toks[0].isdigit() and 1 <= int(toks[0]) <= 10:
                rank, cause = toks[0], " ".join(toks[1:-3])
            elif label == OTHER:
                rank, cause = "other", label
            else:
                continue
            cause = re.sub(r"\s*-\s*", "-", cause)  # PDFium: "Ill - defined"
            for sex, v in zip(SEXES, toks[-3:], strict=True):
                yield {"page": page_no, "rank": rank, "cause": cause, "sex": sex, "value": v}


@check("shares do not add up to 100")
def adds_to_100(df: pd.DataFrame) -> pd.Series:
    """Flag a sex's eleven shares when their sum is off 100 by more than rounding."""
    num = pd.to_numeric(df.value, errors="coerce").groupby([df.page, df.sex])
    n = num.transform("count")
    off = (num.transform("sum") - 100).abs() > 0.05 * n
    return off & (n == 11)
