"""Drop text a reader cannot see: render mode 3, zero opacity, white on a light background."""

import logging
from pathlib import Path
from typing import Any

from ._prepare import replace_each

logger = logging.getLogger(__name__)

Box = tuple[float, float, float, float]
MIN_CONTRAST = 1.5  # white text on a fill with a lower WCAG contrast ratio does not show
NEAR = 0.1  # pt: a glyph is a hidden character when both its x-edges match this closely


def _white(color: tuple, n: int) -> bool:
    """Whether a fill colour of n components is white (CMYK white is all zero)."""
    if not color:
        return False
    if n == 4:
        return all(c <= 0.02 for c in color)
    return all(c >= 0.98 for c in color)


def _hidden_span(span: dict) -> bool:
    """Whether a text-trace span may be unseen: render mode 3, no fill opacity, or white."""
    return span["type"] == 3 or span["opacity"] == 0 or _white(span["color"], span["colorspace"])


def _white_span(span: dict) -> bool:
    """Whether a hidden-looking span is hidden only by being white (a dark fill shows it)."""
    return span["type"] != 3 and span["opacity"] != 0


def _contrast(rgb: tuple) -> float:
    """WCAG contrast ratio of white text on an sRGB fill (1 = invisible, 21 = on black)."""
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb[:3]]
    return 1.05 / (0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2] + 0.05)


def hidden_chars(page: Any) -> list[tuple[str, Box]]:
    """Return (character, bbox) of each character on the page that is drawn but not visible.

    A hidden-looking character over an image (an OCR layer, white text on a photo) is kept.
    """
    import pymupdf

    trace = page.get_texttrace()
    if not any(_hidden_span(s) for s in trace):
        return []
    fills = [  # get_drawings reports fills as RGB; only white text is judged against them
        (d["seqno"], d["rect"], _contrast(d["fill"]))
        for d in (
            page.get_drawings() if any(_hidden_span(s) and _white_span(s) for s in trace) else ()
        )
        if d.get("fill") is not None and "f" in d.get("type", "")
    ]
    images = [pymupdf.Rect(i["bbox"]) for i in page.get_image_info()]
    out = []
    for s in trace:
        if not _hidden_span(s):
            continue
        white_only = _white_span(s)
        for c in s["chars"]:
            x0, y0, x1, y1 = c[3]
            pt = pymupdf.Point((x0 + x1) / 2, (y0 + y1) / 2)
            if any(r.contains(pt) for r in images):
                continue
            if white_only:
                under = [(q, con) for q, rect, con in fills if q < s["seqno"] and rect.contains(pt)]
                if under and max(under)[1] >= MIN_CONTRAST:
                    continue  # white on a coloured fill: a table header
            out.append((chr(c[0]), (x0, y0, x1, y1)))
    return out


def _filter(page: Any, hidden: list[tuple[str, Box]]) -> None:
    """Remove from page's content the glyphs whose boxes match hidden ones."""
    import pymupdf

    mupdf = pymupdf.mupdf
    to_page = page.transformation_matrix

    class Drop(mupdf.PdfSanitizeFilterOptions2):  # type: ignore[name-defined]
        def __init__(self) -> None:
            super().__init__()
            self.use_virtual_text_filter()

        def text_filter(self, *args: Any) -> int:  # ctx, ucsbuf, ucslen, trm, ctm, bbox, ...
            trm, ctm, bbox = args[3:6]
            glyph = mupdf.fz_transform_rect(mupdf.FzRect(bbox), mupdf.FzMatrix(trm))
            r = mupdf.fz_transform_rect(glyph, mupdf.FzMatrix(ctm))
            b = pymupdf.Rect(r.x0, r.y0, r.x1, r.y1) * to_page
            cy = (b.y0 + b.y1) / 2
            for _char, (x0, y0, x1, y1) in hidden:
                if abs(b.x0 - x0) < NEAR and abs(b.x1 - x1) < NEAR and y0 - 1 <= cy <= y1 + 1:
                    return 1
            return 0

    opts = pymupdf._make_PdfFilterOptions(recurse=1, sanitize=1, sopts=Drop())
    pdf_page = pymupdf._as_pdf_page(page.this)
    mupdf.pdf_filter_page_contents(pdf_page.doc(), pdf_page, opts)


def _key(char: str, box: Box) -> tuple[str, int, int]:
    """A character with its centre in 0.2 pt steps."""
    return char, round((box[0] + box[2]) * 2.5), round((box[1] + box[3]) * 2.5)


def _chars(page: Any) -> list[tuple[str, int, int]]:
    """Every drawn character, keyed by _key."""
    return sorted(_key(chr(c[0]), c[3]) for s in page.get_texttrace() for c in s["chars"])


def _cleaned(doc: Any, page: Any) -> Any:
    """A one-page copy of page without its hidden text, or None to keep the page."""
    import pymupdf

    n = page.number
    hidden = hidden_chars(page)
    if not hidden:
        return None
    one = pymupdf.open()
    one.insert_pdf(doc, from_page=n, to_page=n)
    before = _chars(one[0])
    _filter(one[0], hidden)
    gone = {_key(t, b) for t, b in hidden}
    if _chars(one[0]) == [c for c in before if c not in gone]:
        return one
    logger.info("page %d: hidden text could not be removed alone; kept", n + 1)
    one.close()
    return None


def drop_invisible(pdf: Path, out_dir: Path) -> Path:
    """Copy of pdf without text a reader cannot see, or pdf itself.

    Every engine reads text drawn in render mode 3, with zero fill opacity, or in
    white on the bare page or a light fill as if it were printed ("Z.Eggs" for a
    printed "Eggs"). Only those glyphs are removed from the content stream, so
    visible text overlapping them stays; a page whose other text would change is
    kept as printed.
    """
    return replace_each(pdf, out_dir, _cleaned, "invisible text dropped")
