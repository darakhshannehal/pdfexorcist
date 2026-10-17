"""CRS State Table 6: deaths by age group, sex and residence."""

import re
from collections.abc import Iterable, Iterator

from pdfexorcist import parse_by_columns
from pdfexorcist.cells import BoxCell, token_boxes, union
from pdfexorcist.rows import Page

AREAS = ("Rural", "Urban", "Total")
SEXES = ("Male", "Female", "Person")
COLS = [f"{a}_{s}" for a in AREAS for s in SEXES]
KEY = ["page", "state", "age", "col"]
ALL_AGES = "All Ages"
# "Less than 1 Year", "61Year - 65 Year", "66 Year - 70", "81 and above", "Age Not Stated"
AGE = re.compile(
    r"^(Less than 1 Year|\d+ ?Years? ?- ?\d+( ?Years?)?|\d+ ?(Years? ?)?(&|and) ?above"
    r"|(Age )?Not Stated)(?=\s|$)",
    re.I,
)


def _age(label: str) -> str:
    """One spelling per age group: "<1", "1-4", "70+", "Not Stated"."""
    nums = re.findall(r"\d+", label)
    if label.lower().startswith("less"):
        return "<1"
    if "above" in label.lower():
        return f"{nums[0]}+"
    return "-".join(nums) if nums else "Not Stated"


def _glued(cells: list) -> list:
    """The line with an age label (it holds numbers) as one cell, so no part reads as a value."""
    toks = list(token_boxes(cells))
    m = AGE.match(" ".join(t for _, t, _ in toks))
    if not m:
        return cells
    n = len(m.group().split())
    label = BoxCell(toks[0][0], "age:" + _age(m.group()), union([b for *_, b in toks[:n]]))
    return [label, *(BoxCell(x, t, b) for x, t, b in toks[n:])]


def parse(pages: Iterable[Page]) -> Iterator[dict]:
    """Yield values keyed by page, State, age group and column.

    A State's own row is its All Ages total; the age rows below it are its parts.
    Values are placed by both their order and their x; where those disagree (a
    row with "Not Available" over some cells) the cell is left unresolved.
    """
    for page_no, lines in pages:
        state = ""
        page = [(page_no, [_glued(cells) for cells in lines])]
        for cell in parse_by_columns(page, placement="both"):
            label = cell["label"]
            if not label.startswith("age:"):
                state = label  # "" for the column numbers under the header
            if state.lower().startswith("note"):  # a footnote ending "more than 1 year"
                continue
            if not state or cell["col"] >= len(COLS):
                continue
            area, sex = COLS[cell["col"]].split("_")
            yield {
                "page": page_no,
                "state": re.sub(r"[^a-z]", "", state.lower()),
                "age": label[4:] if label.startswith("age:") else ALL_AGES,
                "col": COLS[cell["col"]],
                "label": state,
                "area": area,
                "sex": sex,
                "value": cell["value"],
            }
