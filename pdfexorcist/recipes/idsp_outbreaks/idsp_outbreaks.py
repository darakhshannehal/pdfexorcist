"""IDSP weekly outbreak report (NCDC)."""

import re
from collections.abc import Iterable, Iterator

from pdfexorcist.rows import Page

ID = re.compile(r"^[A-Z]{2}/[A-Z]{2,4}/\d{4}/\d+/\d+$")
INT = re.compile(r"^\d+$")
DATE = re.compile(r"^\d\d-\d\d-(\d{4})?$")
# the statuses this report prints; a new one reads as a comment word
STATUS = {"Under", "Control", "Surveillance", "Investigation", "Controlled", "Contained"}
LATE = "REPORTED LATE"


def _join_numbers(cells: list[tuple[float, str]]) -> list[tuple[float, str]]:
    """Put a number back on the name it starts; rows.group_words splits "24" off "Paraganas"."""
    out: list[tuple[float, str]] = []
    for x, t in cells:
        if out and INT.match(out[-1][1]):
            out[-1] = (out[-1][0], f"{out[-1][1]} {t}")
        else:
            out.append((x, t))
    return out


def _row(cells: list[tuple[float, str]], late: bool) -> "_Row | None":
    """The outbreak a line starts, or None when its cases and deaths are not found."""
    texts = [t for _, t in cells]
    # cases and deaths: two whole numbers, then the start date
    for i in range(3, len(texts) - 2):
        if INT.match(texts[i]) and INT.match(texts[i + 1]) and DATE.match(texts[i + 2]):
            return _Row(cells, i, late)
    return None


class _Row:
    """One outbreak: its columns' x on the first line, and the text read under each."""

    def __init__(self, cells: list[tuple[float, str]], cases: int, late: bool) -> None:
        self.id = cells[0][1]
        self.late = late
        cols = ["state", "district", "disease", "cases", "deaths", "start"]
        cols += [] if late else ["reported"]
        cols += ["status", "comment"]  # comment words stay out of status
        names = _join_numbers(cells[1:cases])  # state, district, then the disease in pieces
        rest = cells[cases:]
        # a disease that starts on a later line still needs an anchor
        xs = [x for x, _ in [*names[:2], names[min(2, len(names) - 1)], *rest]]
        self.anchors = list(zip(xs, cols, strict=False))
        self.text: dict[str, list[str]] = {c: [] for c in cols}
        for x, t in [*names[:2], *rest]:
            self.add(x, t)
        self.text["disease"] += [t for _, t in names[2:]]

    def add(self, x: float, t: str) -> None:
        col = min(self.anchors, key=lambda a: abs(a[0] - x))[1]
        if col != "comment" and (col != "status" or set(t.split()) <= STATUS):
            self.text[col].append(t)

    def values(self) -> Iterator[tuple[str, str]]:
        for col, parts in self.text.items():
            if parts:
                yield col, "".join(parts) if col in ("start", "reported") else _words(parts)


def _words(parts: list[str]) -> str:
    """Join a column's lines, gluing words the narrow columns break without a hyphen.

    A lowercase line after a long capitalised word ("Maharashtr" "a",
    "Gastroenterit" "is") continues it; "Fever with" "rash" stays two words.
    """
    out = parts[0]
    for p in parts[1:]:
        last = out.split()[-1]
        glue = p[0].islower() and last[0].isupper() and len(last) >= 6
        out = f"{out}{p}" if glue else f"{out} {p}"
    return out


def parse(pages: Iterable[Page]) -> Iterator[dict]:
    """Yield each outbreak's columns keyed by its unique ID."""
    late = False
    for page_no, lines in pages:
        row: _Row | None = None
        for line in lines:
            cells = [(x, s.strip()) for x, s in line if s.strip()]
            text = " ".join(t for _, t in cells)
            if LATE in text:
                late = True
            if cells and ID.match(cells[0][1]):
                yield from _emit(row, page_no)
                row = _row(cells, late)
            elif row and text.isupper() and len(text) > 10:  # a heading: the table has ended
                yield from _emit(row, page_no)
                row = None
            elif row:
                for x, t in cells:
                    row.add(x, t)
        yield from _emit(row, page_no)


def _emit(row: _Row | None, page_no: int) -> Iterator[dict]:
    if row is None:
        return
    table = "late" if row.late else "week"
    for col, v in row.values():
        yield {"id": row.id, "col": col, "value": v, "table": table, "page": page_no}
