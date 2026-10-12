"""Turn pages whose table is printed sideways so its text reads left to right."""

import logging
from collections import Counter
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# show_pdf_page rotate that levels each text direction (y down)
_TURNS = {(0, -1): 270, (-1, 0): 180, (0, 1): 90}


Centres = dict[tuple[int, int], list[tuple[float, float]]]


def _centres(page: Any) -> Centres:
    """Return each printed character's centre, by its line's direction rounded to an axis."""
    import pymupdf

    out: Centres = {}
    text = page.get_text("rawdict", flags=pymupdf.TEXTFLAGS_TEXT)
    for block in text["blocks"]:
        for line in block.get("lines", []):
            d = (round(line["dir"][0]), round(line["dir"][1]))
            for span in line["spans"]:
                for c in span["chars"]:
                    if not c["c"].isspace():
                        x0, y0, x1, y1 = c["bbox"]
                        out.setdefault(d, []).append(((x0 + x1) / 2, (y0 + y1) / 2))
    return out


def _turn(page: Any) -> tuple[int, int] | None:
    """Return the direction most characters run in, when it is not left to right."""
    import pymupdf

    count: Counter = Counter()
    for block in page.get_text("dict", flags=pymupdf.TEXTFLAGS_TEXT)["blocks"]:
        for line in block.get("lines", []):
            d = (round(line["dir"][0]), round(line["dir"][1]))
            count[d] += sum(len("".join(s["text"].split())) for s in line["spans"])
    top = max(count, key=count.__getitem__, default=None)
    return top if top in _TURNS else None


def upright_pages(pdf: Path, out_dir: Path) -> Path:
    """Copy of pdf with sideways pages turned upright, or pdf itself.

    Only poppler levels text drawn sideways without /Rotate. Text across the table
    (running heads, folios, slug) is dropped; turned, it would split table rows.
    """
    import pymupdf

    with pymupdf.open(pdf) as doc:
        # ponytail: skips /Rotate pages, which MuPDF and PDFium ignore; fold it in if needed
        dirs = [None if page.rotation else _turn(page) for page in doc]
        if not any(dirs):
            return pdf
        with pymupdf.open() as out:
            for page, d in zip(doc, dirs, strict=True):
                if d is None:
                    out.insert_pdf(doc, from_page=page.number, to_page=page.number)
                    continue
                # a dot per character; a running head's box can overlap table text
                for x, y in (xy for k, v in _centres(page).items() if k != d for xy in v):
                    page.add_redact_annot(pymupdf.Rect(x - 0.3, y - 0.3, x + 0.3, y + 0.3))
                page.apply_redactions(images=0, graphics=0)  # text only; keep images, rules
                w, h = page.rect.width, page.rect.height
                if d[0] == 0:
                    w, h = h, w
                new = out.new_page(width=w, height=h)
                new.show_pdf_page(new.rect, doc, page.number, rotate=_TURNS[d])
            logger.info("%d sideways pages turned upright", sum(map(bool, dirs)))
            out_dir.mkdir(parents=True, exist_ok=True)
            path = out_dir / pdf.name
            out.save(path, no_new_id=True)  # stable bytes: older OCR caches are keyed on them
    return path
