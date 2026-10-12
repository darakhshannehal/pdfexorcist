"""Text-layer engines."""

import functools
import gc
import logging
import os
import re
import shutil
import subprocess
from collections import defaultdict
from collections.abc import Callable, Iterator
from importlib.util import find_spec
from pathlib import Path
from typing import Any

from ._registry import register
from .cells import Box, BoxCell
from .rows import Page, group_words, is_value

logger = logging.getLogger(__name__)


@register("pdftotext")
def pdftotext(pdf: Path) -> Iterator[Page]:
    """Extract layout-preserved text with Poppler."""
    if not shutil.which("pdftotext"):
        raise ImportError("poppler's pdftotext is not on PATH")
    text = subprocess.run(
        ["pdftotext", "-layout", str(pdf), "-"],
        capture_output=True,
        encoding="utf-8",  # Windows defaults to cp1252
        errors="replace",
        check=True,
    ).stdout
    for i, page in enumerate(text.rstrip("\f").split("\f"), start=1):  # no phantom last page
        yield i, _layout_lines(page)


def _layout_lines(text: str) -> list:
    """Cells of fixed-width layout text, x in character columns."""
    return [
        [(m.start() + len(m.group()) / 2, m.group()) for m in re.finditer(r"\S+(?: \S+)*", ln)]
        for ln in text.splitlines()
    ]


@register("pypdf", default=False)
def pypdf_(pdf: Path) -> Iterator[Page]:
    """Extract pypdf's fixed-width layout text."""
    import pypdf

    for i, page in enumerate(pypdf.PdfReader(pdf).pages, start=1):
        yield i, _layout_lines(page.extract_text(extraction_mode="layout"))


PDFJS_INSTALL = "npm install -g pdfjs-dist"


@register("pdfjs", default=False)
def pdfjs_(pdf: Path) -> Iterator[Page]:
    """Extract Mozilla pdf.js text items through Node, a page at a time."""
    import json
    import tempfile

    node, dist = shutil.which("node"), _pdfjs_dist()
    if not node or not dist:
        raise ImportError(f"pdfjs needs Node and pdfjs-dist: {PDFJS_INSTALL}")
    cmd = [node, str(Path(__file__).with_name("_pdfjs.mjs")), str(dist), str(pdf.resolve())]
    with tempfile.TemporaryFile() as log:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=log, encoding="utf-8")
        assert proc.stdout is not None
        try:
            for i, line in enumerate(proc.stdout, start=1):
                yield i, group_words([w for box in json.loads(line) for w in _words(*box)])
            if proc.wait():
                log.seek(0)
                raise subprocess.CalledProcessError(proc.returncode, cmd, stderr=log.read())
        finally:
            if proc.poll() is None:  # stopped early (an error, or the caller stopped reading)
                proc.kill()
                proc.wait()


@functools.lru_cache(maxsize=1)
def _pdfjs_dist() -> Path | None:
    """Find pdfjs-dist: $PDFEXORCIST_PDFJS, else the global npm root."""
    if env := os.environ.get("PDFEXORCIST_PDFJS"):
        return Path(env)
    npm = shutil.which("npm")  # npm.cmd on Windows; a bare name fails there
    if not npm:
        return None
    root = subprocess.run([npm, "root", "-g"], capture_output=True, text=True).stdout.strip()
    dist = Path(root) / "pdfjs-dist"
    return dist if dist.is_dir() else None


def _space_ids(page: Any) -> set[int]:
    """Find space glyphs overprinted on visible glyphs."""
    lines: defaultdict[int, list[tuple[float, float]]] = defaultdict(list)
    for c in page.chars:
        if c["text"] != " ":
            lines[round(c["top"])].append((c["x0"], c["x1"]))
    stray = set()
    for c in page.chars:
        if c["text"] == " ":
            mid = (c["x0"] + c["x1"]) / 2
            near = (lines.get(round(c["top"]) + d, ()) for d in (-2, -1, 0, 1, 2))
            if any(a < mid < b for ln in near for a, b in ln):
                stray.add(id(c))
    return stray


def _not_in(ids: set[int]) -> Callable[[Any], bool]:
    """Filter objects whose ids are absent from ids."""
    return lambda o: id(o) not in ids


def _inside(box: tuple, x0: float, y0: float, x1: float, y1: float) -> bool:
    """Test whether a box center lies inside box."""
    return box[0] <= (x0 + x1) / 2 <= box[2] and box[1] <= (y0 + y1) / 2 <= box[3]


@register("pdfplumber")
def pdfplumber_(pdf: Path) -> Iterator[Page]:
    """Extract pdfplumber words grouped into lines."""
    import pdfplumber

    with pdfplumber.open(pdf) as doc:
        for i, raw in enumerate(doc.pages, start=1):
            page = raw.filter(_not_in(_space_ids(raw)))
            words = [  # pdfminer reads text drawn outside the page box; poppler doesn't
                w
                for w in page.extract_words(use_text_flow=False)
                if _inside(raw.bbox, w["x0"], w["top"], w["x1"], w["bottom"])
            ]
            yield (
                i,
                group_words([(w["x0"], w["x1"], w["bottom"], w["text"], w["top"]) for w in words]),
            )
            raw.close()


@register("pymupdf")
def pymupdf_(pdf: Path) -> Iterator[Page]:
    """Extract PyMuPDF words grouped into lines."""
    import pymupdf

    with pymupdf.open(pdf) as doc:
        for i, page in enumerate(doc, start=1):
            words = page.get_text(
                "words", flags=pymupdf.TEXTFLAGS_WORDS & ~pymupdf.TEXT_MEDIABOX_CLIP
            )
            turn = page.rotation_matrix  # words come unrotated
            rects = [(pymupdf.Rect(w[:4]) * turn, w[4]) for w in words]
            yield i, group_words([(r.x0, r.x1, r.y1, t, r.y0) for r, t in rects])


def _n_values(lines: list) -> int:
    """Count single-value cells."""
    return sum(
        1 for line in lines for _, text in line if len(text.split()) == 1 and is_value(text.strip())
    )


@register("camelot")
def camelot_(pdf: Path) -> Iterator[Page]:
    """Extract tables with Camelot's best flavor."""
    try:
        yield from _camelot_pages(pdf)
    finally:
        # camelot 2 holds the PDF open in ref cycles; Windows cannot delete an open file
        gc.collect()


def camelot_ml() -> bool:
    """Whether camelot-py[ml] is installed."""
    return all(find_spec(m) for m in ("torch", "transformers", "timm"))


def _camelot_pages(pdf: Path) -> Iterator[Page]:
    import camelot
    import pymupdf

    with pymupdf.open(pdf) as doc:
        n_pages = doc.page_count
        # camelot: y up from the media box corner; flip to pdfplumber's frame
        boxes = [(p.mediabox.x0, p.mediabox.y0, p.mediabox.height) for p in doc]
    flavors = ["lattice", "stream", "network", "hybrid"]
    if camelot_ml():  # a partial ml install imports torch and queries the Hub before failing
        flavors.append("ml")
    for i in range(1, n_pages + 1):
        reads: list = []
        dx, dy, h = boxes[i - 1]
        for flavor in flavors:
            try:
                tables = camelot.read_pdf(str(pdf), pages=str(i), flavor=flavor)
            except (
                ValueError,
                IndexError,
                ZeroDivisionError,
                ImportError,  # ml on a broken install
            ) as e:  # blank/figure pages
                logger.debug("camelot %s page %d: %s", flavor, i, e)
                continue
            reads.append(
                [
                    [
                        BoxCell(
                            ((b := t.cells[r][j]).x1 + b.x2) / 2,
                            c.replace("\n", " "),
                            (b.x1 + dx, h - b.y2 - dy, b.x2 + dx, h - b.y1 - dy),
                        )
                        for j, c in enumerate(row)
                        if c
                    ]
                    for t in _distinct(tables)
                    for r, row in enumerate(t.df.itertuples(index=False))
                ]
            )
        yield i, max(reads, key=_n_values, default=[])


def _distinct(tables: Any) -> list:
    """Drop tables mostly inside a larger one; network and hybrid repeat rows across them."""

    def overlap(a: Box, b: Box) -> float:
        return max(min(a[2], b[2]) - max(a[0], b[0]), 0) * max(min(a[3], b[3]) - max(a[1], b[1]), 0)

    boxes = [t._bbox for t in tables]
    area = [overlap(b, b) for b in boxes]
    kept: list[int] = []
    for i in sorted(range(len(tables)), key=lambda i: area[i], reverse=True):
        if all(overlap(boxes[i], boxes[k]) < area[i] / 2 for k in kept):
            kept.append(i)
    return [tables[i] for i in sorted(kept)]


def _split_cells(row: list) -> list:
    """Split Tabula cells into positioned tokens."""
    out = []
    for c in row:
        text = c.get("text", "").replace("\r", " ")
        top, bottom = c.get("top", 0.0), c.get("top", 0.0) + c.get("height", 0.0)
        out += [
            BoxCell((a + b) / 2, t, (a, top, b, bottom))
            for a, b, t in _spans(c["left"], c["left"] + c["width"], text)
        ]
    return out


def _words(x0: float, x1: float, y_top: float, y_bottom: float, text: str) -> list:
    """Split a text box into positioned tokens."""
    return [(a, b, y_bottom, t, y_top) for a, b, t in _spans(x0, x1, text)]


def _spans(x0: float, x1: float, text: str) -> list:
    """Position each token within a text box."""
    width = max(len(text), 1)
    return [
        (
            x0 + (x1 - x0) * m.start() / width,
            x0 + (x1 - x0) * m.end() / width,
            m.group(),
        )
        for m in re.finditer(r"\S+", text)
    ]


@register("tabula", default=False)
def tabula_(pdf: Path) -> Iterator[Page]:
    """Extract tables with Tabula's best flavor."""
    import pymupdf
    import tabula

    with pymupdf.open(pdf) as doc:
        n_pages = doc.page_count
    for i in range(1, n_pages + 1):
        reads = []
        for lattice in (True, False):
            try:
                tables = tabula.read_pdf(
                    str(pdf),
                    pages=i,
                    lattice=lattice,
                    stream=not lattice,
                    multiple_tables=True,
                    output_format="json",
                    silent=True,
                )
            except Exception as e:  # noqa: BLE001 - tabula surfaces Java errors as generic exceptions
                logger.debug("tabula page %d: %s", i, e)
                continue
            reads.append(
                [cells for t in tables for row in t.get("data", []) if (cells := _split_cells(row))]
            )
        yield i, max(reads, key=_n_values, default=[])


@register("pdfium")
def pdfium_(pdf: Path) -> Iterator[Page]:
    """Extract PDFium glyphs grouped into words by gap, then into lines."""
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(str(pdf))
    try:
        for i, page in enumerate(doc, start=1):
            tp = page.get_textpage()
            yield i, group_words(_pdfium_words(page, tp))
            tp.close()
            page.close()
    finally:
        doc.close()


def _pdfium_words(page: Any, tp: Any) -> list:
    """Group PDFium glyphs into words by gap; PDFium's own text runs span empty columns."""
    from pdfplumber.utils.text import WordExtractor

    rot = page.get_rotation()
    w, h = page.get_size()  # displayed; glyph boxes are unrotated
    box = page.get_bbox()
    chars: list[dict] = []
    seen: dict[tuple, list[dict]] = {}  # (text, x, y) on a 1 pt grid
    for j, ch in enumerate(tp.get_text_range()):
        # tight boxes gap around "."
        left, b, r, t = tp.get_charbox(j, loose=True)
        if r <= left or not _inside(box, left, b, r, t):
            continue  # generated (zero-width) glyph, or outside the page box
        x0, top, x1, bottom = _displayed(left, b, r, t, rot, w, h)
        gx, gy = int(x0), int(top)
        near = (
            k
            for dx in (-1, 0, 1)
            for dy in (-1, 0, 1)
            for k in seen.get((ch, gx + dx, gy + dy), ())
        )
        # fake bold redraws a glyph a fraction of a point off; ligature letters are neighbours
        if any(abs(k["x0"] - x0) < 1 and abs(k["top"] - top) < 1 and j - k["j"] != 1 for k in near):
            continue
        c = {
            "text": ch,
            "x0": x0,
            "x1": x1,
            "top": top,
            "bottom": bottom,
            "doctop": top,
            "upright": True,
            "j": j,
        }
        seen.setdefault((ch, gx, gy), []).append(c)
        chars.append(c)
    words = WordExtractor().iter_extract_tuples(chars)
    return [(wd["x0"], wd["x1"], wd["bottom"], wd["text"], wd["top"]) for wd, _ in words]


def _displayed(
    left: float, b: float, r: float, t: float, rot: int, w: float, h: float
) -> tuple[float, float, float, float]:
    """Map an unrotated PDF box (y up) to a displayed w x h page: x0, top, x1, bottom."""
    if rot == 90:
        return b, left, t, r
    if rot == 180:
        return w - r, b, w - left, t
    if rot == 270:
        return w - t, h - r, w - b, h - left
    return left, h - t, r, h - b
