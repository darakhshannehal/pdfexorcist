"""Lines to keyed cells."""

import re
import statistics
from collections import Counter
from collections.abc import Iterable, Iterator
from itertools import pairwise

from ._bold import drop_copies
from .cells import Box, BoxCell, token_boxes, union

Cell = tuple[float, str]  # engines may pass a BoxCell: the same pair plus .box
Page = tuple[int, list[list[Cell]]]

# nc: "no cases" (NFHS-5); 2E+05, #####: Excel's display of a number too wide for its cell
# read as values so columns stay in place; checks.lossy fails them
LOSSY_FORMS = r"\d(\.\d+)?E\+\d+|#{3,}|#(REF!|VALUE!|DIV/0!|NAME\?)"
VALUE = re.compile(
    r"^\(?[-−]?\d[\d,]*([.·]\d+)?%?\)?[*#@$]?$|^(\*|-|–|—|\.\.\.?|…|--|na|NA|nc|NC|n/a|N/A|N\.A\.|n\.a\.|#N/A|"
    + LOSSY_FORMS
    + ")$"
)
KEY = ["page", "row", "col"]
PLACEMENTS = ("x", "both")


def is_value(tok: str) -> bool:
    """Return whether a token matches a printed table value."""
    return bool(VALUE.match(tok))


def label_key(label: str) -> str:
    """Return a case-, spacing-, and punctuation-insensitive label key."""
    return re.sub(r"[^a-z0-9]", "", label.lower())


def split_values(cells: list[Cell]) -> tuple[str, list[str]]:
    """Split a line into label text and trailing value tokens."""
    toks = [t for _, text in cells for t in text.split()]
    i = len(toks)
    while i and is_value(toks[i - 1]):
        i -= 1
    return " ".join(toks[:i]), toks[i:]


def parse_rows(pages: Iterable[Page], min_values: int = 1) -> Iterator[dict]:
    """Default parser: one dict per value, keyed by KEY, plus the label text.

    A trailing number in a label ("Population 2019") is read as a value; pass a
    document parser to extract() when that matters.
    """
    for page_no, lines in pages:
        seen: Counter = Counter()
        for cells in lines:
            label, vals = split_values(cells)
            if len(vals) < min_values:  # e.g. 2: skip a title ending in its year
                continue
            key = label_key(label)
            seen[key] += 1
            boxes = [b for _, _, b in token_boxes(cells)][-len(vals) :]
            for col, v in enumerate(vals):
                cell = {
                    "page": page_no,
                    "row": f"{key}#{seen[key]}",
                    "col": col,
                    "label": label,
                    "value": v,
                }
                if boxes[col] is not None:  # where the engine saw it (BoxCell lines)
                    cell["box"] = boxes[col]
                yield cell


def group_words(words: list[tuple], gap: float = 8.0) -> list[list[Cell]]:
    """(x0, x1, y_bottom, text[, y_top]) words to lines of (x_centre, text) BoxCells.

    A word joins a line when it overlaps the line's first word by half the shorter
    height; a word without y_top is 1 pt tall. Copies of a word drawn again within
    COPY_PT (fake bold) count once.
    Label words within gap pt join one cell; values never join.
    """
    boxes = [(w[0], w[1], w[4] if len(w) > 4 else w[2] - 1, w[2], w[3]) for w in words]
    boxes = drop_copies(boxes)
    rows: list[list] = []  # [anchor top, anchor bottom, words]
    for x0, x1, top, bottom, t in sorted(boxes, key=lambda b: ((b[2] + b[3]) / 2, b[0])):
        word = (x0, x1, t, top, bottom)
        if rows:
            r = rows[-1]
            overlap = min(r[1], bottom) - max(r[0], top)
            if overlap >= 0.5 * min(r[1] - r[0], bottom - top):
                r[2].append(word)
                continue
        rows.append([top, bottom, [word]])
    out: list[list[Cell]] = []
    for _, _, row in rows:
        row.sort(key=lambda w: w[0])
        cells: list[list] = []  # [x0, x1, text, top, bottom]
        for x0, x1, t, top, bottom in row:
            joinable = (
                cells
                and x0 - cells[-1][1] <= gap
                and not (is_value(t) or is_value(cells[-1][2].split()[-1]))
            )
            if joinable:
                cells[-1][1], cells[-1][2] = x1, cells[-1][2] + " " + t
                cells[-1][3] = min(cells[-1][3], top)
                cells[-1][4] = max(cells[-1][4], bottom)
            else:
                cells.append([x0, x1, t, top, bottom])
        out.append([BoxCell((a + b) / 2, t, (a, y0, b, y1)) for a, b, t, y0, y1 in cells])
    return out


def parse_by_columns(
    pages: Iterable[Page], min_values: int = 2, tol: float = 0.45, placement: str = "x"
) -> Iterator[dict]:
    """Like parse_rows, but a value's column comes from its x.

    Column centres are the median x of the i-th value over rows with the page's
    most common value count; each value goes to the nearest centre within tol x
    the spacing, so a value an engine missed shifts nothing. Tokens in one column
    are joined ("1" "437" -> "1437").

    placement="both" also places values by their order and keeps a cell only where
    the two agree. Where they differ the engine reads both values there (a blank
    reads ""), so it loses its vote on that cell and the vote shows both readings.
    A row with fewer values than the page's mode is skipped when one of its values
    has no column by x.
    """
    if placement not in PLACEMENTS:
        raise ValueError(f"placement must be 'x' or 'both', got {placement!r}")
    for page_no, lines in pages:
        rows = []  # (label, [(x, value token, its box or None)])
        for cells in lines:
            toks = list(token_boxes(cells))
            label = " ".join(t for _, t, _ in toks if not is_value(t))
            rows.append((label, [tok for tok in toks if is_value(tok[1])]))
        counts = Counter(len(v) for _, v in rows if len(v) >= min_values)
        if not counts:
            continue
        k = counts.most_common(1)[0][0]
        full = [v for _, v in rows if len(v) == k]
        centres = [statistics.median(v[i][0] for v in full) for i in range(k)]
        spacing = min((b - a for a, b in pairwise(centres)), default=1.0) or 1.0
        seen: Counter = Counter()
        for label, vals in rows:
            if len(vals) < min_values:
                continue
            cols = [_column(x, centres, tol * spacing) for x, _, _ in vals]
            if placement == "both" and len(vals) < k and None in cols:
                continue  # an engine that dropped a value and misplaced another
            placed: dict[int, list[tuple[str, Box | None]]] = {}
            for c, (_, t, b) in zip(cols, vals, strict=True):
                if c is not None:
                    placed.setdefault(c, []).append((t, b))
            key = label_key(label)
            seen[key] += 1
            by_x = {
                c: ("".join(t for t, _ in ts), union([b for _, b in ts]))
                for c, ts in placed.items()
            }
            if placement == "x":
                readings = [(c, v, b) for c, (v, b) in sorted(by_x.items())]
            else:
                readings = _both(by_x, vals)
            for col, value, box in readings:
                if value and not is_value(value):
                    continue
                cell = {
                    "page": page_no,
                    "row": f"{key}#{seen[key]}",
                    "col": col,
                    "label": label,
                    "value": value,
                }
                if box is not None:
                    cell["box"] = box
                yield cell


def _column(x: float, centres: list[float], within: float) -> int | None:
    """Index of the centre nearest x, or None when it is further than within."""
    c = min(range(len(centres)), key=lambda i: abs(centres[i] - x))
    return c if abs(centres[c] - x) <= within else None


def _both(by_x: dict, vals: list) -> list[tuple[int, str, Box | None]]:
    """Readings where x and order agree, and both readings where they do not."""
    by_order = {i: (t, b) for i, (_, t, b) in enumerate(vals)}
    out = []
    for c in sorted(by_x.keys() | by_order.keys()):
        (a, box), (b, _) = by_order.get(c, ("", None)), by_x.get(c, ("", None))
        out += [(c, a, box)] if a == b else [(c, a, box), (c, b, box)]
    return out
