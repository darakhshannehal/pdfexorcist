"""NSS KI 75/25.0 (Health), Appendix A: the detailed tables, by sector, gender or State."""

import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator

import pandas as pd

from pdfexorcist import check
from pdfexorcist.rows import Cell, Page, is_value, label_key, split_values

TABLE = re.compile(r"^Table (A\d+):")
# a side label: on its own line, in a row's first cell, or joined to the label (pdftotext)
SECTOR = re.compile(r"^(Rural\s*\+(\s*Urban)?|Rural|Urban|\+)$")
GROUP = re.compile(r"^(Male|Female|All)$")
GLUED = re.compile(r"^(Rural\s*\+(\s*Urban)?|Rural|Urban|Male|Female)\s+(?=\S)")
# A26 names its sector in the page header, beside "all-India"
HEADER = re.compile(r"^all-India\s+(Rural \+ Urban|Rural|Urban)$")
# "below 20" ends in a number that split_values takes for a value (A27)
BOUND = {"below", "above", "under", "upto"}
# "Private hospital: All" heads the rows below it ("Normal delivery", A30)
PREFIX = re.compile(r"^(.+?)\s*:\s*\S")

Line = tuple[int, str, str, list[Cell]]  # page, table, page sector, cells


def _text(cell: Cell) -> str:
    return " ".join(cell[1].split())


def _lines(pages: Iterable[Page]) -> Iterator[Line]:
    """The lines of each table; an empty line marks a page break or a table title."""
    table = ""
    for page_no, lines in pages:
        page_sector = ""
        yield page_no, table, "", []
        for cells in lines:
            text = " ".join(_text(c) for c in cells)
            if m := TABLE.match(text):
                table = m.group(1)
                yield page_no, table, "", []
            elif m := HEADER.match(text):
                page_sector = m.group(1)
            elif table and cells:
                yield page_no, table, page_sector, cells


def _side_cells(lines: list[Line]) -> dict[str, set[str]]:
    """Per table, the first-cell texts that are side labels.

    A sector or gender word, or a State name: a first cell that the same row label follows
    beside several different first cells ("Andhra Pradesh | government/public hospital",
    "Assam | government/public hospital"). A heading ending in ":" is not one.
    """
    pairs: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for _, table, _, cells in lines:
        if (
            len(cells) > 1
            and not is_value(cells[0][1].strip())
            and not is_value(cells[1][1].strip())
        ):
            pairs[table][_text(cells[1])].add(_text(cells[0]))
    out: dict[str, set[str]] = defaultdict(set)
    for table, by_label in pairs.items():
        for firsts in by_label.values():
            many = len(firsts) > 1
            out[table] |= {
                f
                for f in firsts
                if SECTOR.match(f) or GROUP.match(f) or (many and not f.endswith(":"))
            }
    return out


def _name(texts: list[str]) -> dict[str, str]:
    """Sector, group and area of a block from its side labels ("Rural +" and "Urban" join)."""
    sector = " ".join(t for t in texts if SECTOR.match(t))
    sector = re.sub(r"\s*\+\s*", " + ", sector).strip()
    if "Rural" in sector and "Urban" in sector:
        sector = "Rural + Urban"
    group = next((t for t in texts if GROUP.match(t)), "")
    area = next((t for t in texts if not SECTOR.match(t) and not GROUP.match(t)), "")
    return {"sector": sector, "group": group, "area": area}


def parse(pages: Iterable[Page]) -> Iterator[dict]:
    """Yield each value keyed by table, block, row and column, with sector, group and area.

    A block starts where the table's first row label comes back. Its sector (Rural, Urban,
    Rural + Urban), group (Male, Female, All) and area (a State/UT) are the side labels read
    in it, or the page header for the sector; a block without one leaves them empty.
    """
    lines = list(_lines(pages))
    sides = _side_cells(lines)
    parsed = []
    for page_no, table, page_sector, cells in lines:
        lead = ""
        if len(cells) > 1 and _text(cells[0]) in sides[table] and not is_value(cells[1][1].strip()):
            lead, cells = _text(cells[0]), cells[1:]
        label, vals = split_values(cells)
        parsed.append((page_no, table, page_sector, lead, " ".join(label.split()), vals))
    # modal row width per table
    width = {
        t: Counter(len(v) for _, tt, _, _, lab, v in parsed if tt == t and lab and v).most_common(
            1
        )[0][0]
        for t in {p[1] for p in parsed if p[4] and p[5]}
    }
    rows: list[dict] = []
    first: dict[str, str] = {}
    labels: dict[str, set[str]] = defaultdict(set)
    side: dict[tuple[str, int], list[str]] = defaultdict(list)
    header: dict[tuple[str, int], str] = {}
    starts: Counter[str] = Counter()
    seen: Counter[tuple[str, int, str]] = Counter()
    above, prefix = "", ""
    for page_no, table, page_sector, lead, label, vals in parsed:
        if not label and not vals:  # page break or table title
            above = ""
            continue
        if not vals and (SECTOR.match(label) or GROUP.match(label) or label in sides[table]):
            if starts[table]:  # before the first row it is a column heading
                side[(table, starts[table])].append(label)
            above = ""  # values take the label of the line just above them only
            continue
        if (g := GLUED.match(label)) and label_key(label[g.end() :]) in labels[table]:
            lead, label = " ".join(g.group(0).split()), label[g.end() :]
        if (
            label.split()[-1:]
            and label.split()[-1].lower() in BOUND
            and len(vals) == width[table] + 1
        ):
            label, vals = f"{label} {vals[0]}", vals[1:]
        if not vals:
            above = label
            continue
        # wrapped label: some engines put its values on the next, unlabelled line (A25)
        label, above = label or above, ""
        if not label:
            continue
        if label_key(label) == first.setdefault(table, label_key(label)):
            starts[table] += 1
            prefix = ""
        block = max(starts[table], 1)
        if pm := PREFIX.match(label):
            prefix = pm.group(1)
        elif prefix:
            label = f"{prefix}: {label}"
        if lead:
            side[(table, block)].append(lead)
        if page_sector:
            header[(table, block)] = page_sector
        key = label_key(label)
        labels[table].add(label_key(label.split(": ")[-1]))
        seen[(table, block, key)] += 1
        n = seen[(table, block, key)]
        for col, v in enumerate(vals):
            rows.append({"page": page_no, "table": table, "block": block, "label": label, "n": n,
                         "row": f"{key}#{n}", "col": col, "value": v})  # fmt: skip
    for r in rows:
        name = _name(side.get((r["table"], r["block"]), []))
        name["sector"] = name["sector"] or header.get((r["table"], r["block"]), "")
        r.update(name)
        yield r


@check("parts do not add up to the 100.0 of their all row")
def shares_add_up(df: pd.DataFrame) -> pd.Series:
    """In a block whose "all" row is 100.0 in every column, the other rows add up to 100."""
    num = df.assign(v=pd.to_numeric(df.value, errors="coerce"))
    bad = pd.Series(False, index=df.index)
    for _, b in num.groupby(["table", "block"]):
        total = b[b.label.str.lower() == "all"]
        if total.empty or not (total.v == 100.0).all():
            continue
        parts = b.drop(total.index).groupby("col").v.sum(min_count=1)
        off = parts[(parts - 100).abs() > 0.5].index
        bad |= df.index.isin(b[b.col.isin(off)].index)
    return bad
