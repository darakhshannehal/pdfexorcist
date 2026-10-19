"""CBHI National Health Profile: State/UT wise malaria cases and deaths."""

import re
from collections.abc import Iterable, Iterator

from pdfexorcist.rows import Page, split_values

YEAR = re.compile(r"\b(20\d\d)\b(\s*\(till)?")
MEASURES = ("Cases", "Deaths")


def _header(text: str) -> list[str] | None:
    """Column years from the header line, "2022 (Prov.)" for a provisional year."""
    years = [y + (" (Prov.)" if till else "") for y, till in YEAR.findall(text)]
    return years if len(years) >= 3 else None


def _rows(lines: list) -> Iterator[tuple[str, str, list[str]]]:
    """Yield (serial, name, values) for each row; a wrapped name takes its next line."""
    split = [split_values(cells) for cells in lines]
    for i, (label, vals) in enumerate(split):
        if not vals or not label:
            continue
        nxt = split[i + 1] if i + 1 < len(split) else ("", [])
        if nxt[0] and not nxt[1] and not nxt[0].startswith("Source"):
            label = f"{label} {nxt[0]}"  # "Andaman & Nicobar" / "Islands"
        sno, _, name = label.partition(" ")
        if not sno.isdigit():
            sno, name = "", label
        yield sno, name, vals


def parse(pages: Iterable[Page]) -> Iterator[dict]:
    """Yield one value per State/UT, year and measure, with India as a row."""
    for page_no, lines in pages:
        texts = (" ".join(t for _, t in cells) for cells in lines)
        heads = ((i, _header(t)) for i, t in enumerate(texts) if "State" in t)
        start, years = next(((i, y) for i, y in heads if y), (0, None))
        if years is None:
            continue
        body = lines[start + 1 :]
        cols = [(y, m) for y in years for m in MEASURES]
        for sno, name, vals in _rows(body):
            if len(vals) % 2 or len(vals) > len(cols):
                continue
            for (year, measure), v in zip(cols, vals, strict=False):
                yield {
                    "page": page_no,
                    "state": name,
                    "col": f"{year} {measure}",
                    "sno": sno,
                    "year": year[:4],
                    "measure": measure,
                    "value": v,
                }
