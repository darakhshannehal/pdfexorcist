"""CRS District Tables 7-10: births, deaths, infant deaths and still births by district."""

import re
from collections.abc import Iterable, Iterator

from pdfexorcist import parse_by_columns
from pdfexorcist.cells import BoxCell, token_boxes, union
from pdfexorcist.rows import Page, is_value

AREAS = ("Rural", "Urban", "Total")
SEXES = ("Male", "Female", "Person")
COLS = [*(f"{a}_{s}" for a in AREAS for s in SEXES), "SRB"]  # SRB: Table 7 only
KEY = ["page", "state", "district", "col"]
TABLE = re.compile(r"TABLE\s*-?\s*(\d+)\s*:")
SERIAL = re.compile(r"^\d{1,3}$")
GLUED = re.compile(r"^(\d{1,3})([A-Za-z].*)$")


def _glued(cells: list) -> tuple[str, list]:
    """(serial, the line with its name as one cell); a name can hold a number ("24 Parganas").

    The name runs to its last word before two values in a row.
    """
    toks = list(token_boxes(cells))
    serial = ""
    if toks and (m := GLUED.match(toks[0][1])):  # "1NorthGoa": some engines miss the gap
        serial, toks[0] = m.group(1), (toks[0][0], m.group(2), toks[0][2])
    elif len(toks) > 1 and SERIAL.match(toks[0][1]) and not is_value(toks[1][1]):
        serial, toks = toks[0][1], toks[1:]
    end = 0
    for i, (_, t, _) in enumerate(toks):
        if i + 1 < len(toks) and is_value(t) and is_value(toks[i + 1][1]):
            break
        if not is_value(t):
            end = i + 1
    if not end:
        return serial, cells
    name = "_".join(t for _, t, _ in toks[:end])  # one token, never a value
    return serial, [
        BoxCell(toks[0][0], name, union([b for *_, b in toks[:end]])),
        *(BoxCell(x, t, b) for x, t, b in toks[end:]),
    ]


def _key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def parse(pages: Iterable[Page]) -> Iterator[dict]:
    """Yield values keyed by page, State, district and column.

    A row without a serial number is a State (its total); numbered rows below it
    are its districts. A page's first districts keep the last page's State when
    their serial numbers go on from it; else (a page before them not read) their
    State is "". Values are placed by order and by position and kept only where
    the two agree.
    """
    state, last = "", 0  # the last State and district serial read
    for page_no, lines in pages:
        text = "\n".join(" ".join(t for _, t in cells) for cells in lines)
        table = m.group(1) if (m := TABLE.search(text)) else ""
        serials: dict[str, int] = {}
        glued = []
        for cells in lines:
            serial, line = _glued(cells)
            if serial and line:
                serials[line[0][1]] = int(serial)
            glued.append(line)
        carry, state, first = state, "", last + 1
        for cell in parse_by_columns([(page_no, glued)], placement="both"):
            name = cell["label"].replace("_", " ")
            # not _key(name): "……", slanted "Not Available" that poppler >= 26 reads as its own line
            if not _key(name) or name.lower().startswith(("note", "sl.", "no.")):
                continue
            serial = serials.get(cell["label"], 0)
            if not serial:
                state = name
            elif first and not state:  # the page's first district
                state = carry if serial == first else ""  # the page goes on with the last State
            first = 0 if serial else first
            last = serial or last
            district = name if serial else ""
            if cell["col"] >= len(COLS):
                continue
            col = COLS[cell["col"]]
            parts = col.split("_")  # "SRB" is its own area and sex
            yield {
                "page": page_no,
                "table": table,
                "state": _key(state),
                "district": _key(district),
                "col": col,
                "label": district or state,
                "serial": serial or "",
                "level": "District" if district else "State",
                "area": parts[0],
                "sex": parts[-1],
                "value": cell["value"],
            }
