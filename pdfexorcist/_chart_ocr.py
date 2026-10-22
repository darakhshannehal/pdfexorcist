"""Value boxes of chart images, read by each OCR engine and voted."""

import io
import logging
import re
import tempfile
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pandas as pd

from ._ocr_engines import UPRIGHT

logger = logging.getLogger(__name__)

SCALE = 3  # crops are enlarged this much; OCR engines miss small digits
HEIGHT = 90  # a short number goes to this height: Apple Vision misses a lone small digit
BORDER = 30  # white pixels around a crop
GAP = 40  # white pixels between crops on a tiled page
DPI = 300  # engines render tiled pages at this resolution: crops stay full size
CHUNKS = 3  # parts an engine that reads in its own process reads at once


def prepare(pixels: Any, style: str) -> tuple[Any, float]:
    """Gray crop with dark text on white, enlarged and bordered; binary applies Otsu's threshold."""
    import cv2

    g = cv2.cvtColor(pixels, cv2.COLOR_RGB2GRAY)
    if g.mean() < 128:  # light text on a dark fill
        g = 255 - g
    short = g.shape[1] < 1.5 * g.shape[0]  # one or two digits; larger crops read worse
    k = max(SCALE, HEIGHT / g.shape[0]) if short else SCALE
    g = cv2.resize(g, None, fx=k, fy=k, interpolation=cv2.INTER_CUBIC)
    if style == "binary":
        _, g = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        if g.mean() < 128:
            g = 255 - g
    return cv2.copyMakeBorder(g, BORDER, BORDER, BORDER, BORDER, cv2.BORDER_CONSTANT, value=255), k


def _tiled(crops: list[tuple[Any, float]]) -> tuple[Any, list[tuple[int, int, float]]]:
    """One image of the crops stacked top to bottom, and the pixel rows and scale of each."""
    import numpy as np

    width = max(c.shape[1] for c, _ in crops)
    bands, rows, y = [], [], 0
    for c, k in crops:
        pad = np.full((c.shape[0], width), 255, dtype=np.uint8)
        pad[:, : c.shape[1]] = c
        bands += [pad, np.full((GAP, width), 255, dtype=np.uint8)]
        rows.append((y, y + c.shape[0], k))
        y += c.shape[0] + GAP
    return np.vstack(bands), rows


def to_pdf(pages: list[Any], path: Path) -> None:
    """A PDF with one page for each gray image, at DPI."""
    import pymupdf
    from PIL import Image

    doc = pymupdf.open()
    for img in pages:
        buf = io.BytesIO()
        Image.fromarray(img).save(buf, format="PNG")
        h, w = img.shape
        page = doc.new_page(width=w * 72 / DPI, height=h * 72 / DPI)
        page.insert_image(page.rect, stream=buf.getvalue())
    doc.set_metadata({"producer": UPRIGHT})
    doc.save(path)


def boxed_cells(lines: list) -> Iterator[tuple[tuple[float, ...], str]]:
    """((x0, y0, x1, y1) in pixels of a DPI page, text) of each cell that has a box."""
    from .cells import cell_box

    for cell in (c for line in lines for c in line):
        if (b := cell_box(cell)) is not None:
            yield tuple(v * DPI / 72 for v in b), cell[1]


def _tokens(text: str) -> list[tuple[float, float, str]]:
    """(start, end, number) of each number in an OCR reading, as parts of its length.

    Indian and western commas, and spaces inside a number, are dropped.
    """
    clean = re.sub(r"(?<=\d)[,\s](?=\d{2,3}\b)", "", text)
    n = max(len(clean), 1)
    return [(m.start() / n, m.end() / n, m.group()) for m in re.finditer(r"\d+(?:\.\d+)?", clean)]


def ocr_pages(engine: str, images: list[Any], tmp: Path, **options: Any) -> dict[int, list]:
    """page number (from 1) -> the engine's lines, for each gray image as one page.

    Engines that read in their own process (ocrmac, tesseract) read CHUNKS parts at once.
    """
    from .extractors import EXTRACTORS

    k = CHUNKS if engine in ("ocrmac", "tesseract") else 1
    size = max(1, -(-len(images) // k))
    parts = [(i, images[i : i + size]) for i in range(0, len(images), size)]

    def one(first: int, part: list[Any]) -> dict[int, list]:
        pdf = tmp / f"{engine}-{first}.pdf"
        to_pdf(part, pdf)
        return {first + no: lines for no, lines in EXTRACTORS[engine](pdf, **options)}

    with ThreadPoolExecutor(len(parts)) as pool:
        return {no: v for got in pool.map(lambda p: one(*p), parts) for no, v in got.items()}


def _readings(engine: str, pages: dict[int, list], rows: list[list]) -> list[dict]:
    """One row per number the engine read: method, chart, box, x0 and x1 in the crop, value."""
    found = []
    for page_no, lines in pages.items():
        bands = rows[page_no - 1]
        for (x0, y0, x1, y1), text in boxed_cells(lines):
            i = next((i for i, (a, b, _) in enumerate(bands) if a <= (y0 + y1) / 2 <= b), None)
            if i is None:
                continue
            k = bands[i][2]
            for a, b, v in _tokens(text):
                lo, hi = (x0 + (x1 - x0) * t for t in (a, b))
                place = {"x0": (lo - BORDER) / k, "x1": (hi - BORDER) / k}
                found.append(
                    {"method": engine, "chart": page_no - 1, "box": i, **place, "value": v}
                )
    return found


def _slots(found: pd.DataFrame) -> pd.DataFrame:
    """found with token (each number's place in its box) and x (the place's centre).

    Places go by position: engines split a crop that holds several numbers differently.
    """
    f = found.assign(x=(found.x0 + found.x1) / 2).sort_values(["chart", "box", "x"])
    gap = (f.x1 - f.x0).median() / 2
    same = (f.chart == f.chart.shift()) & (f.box == f.box.shift())
    f = f.assign(token=((f.x.diff() > gap) & same).groupby([f.chart, f.box]).cumsum())
    f = f.assign(x=f.groupby(["chart", "box", "token"]).x.transform("mean"))
    return f.drop(columns=["x0", "x1"])


def _engine(engine: str, charts: list[list[Any]], style: str, tmp: Path) -> list[dict] | None:
    """The engine's readings of every crop, or None when it is missing or fails."""
    pages, rows = [], []
    for crops in charts:
        img, bands = _tiled([prepare(c, style) for c in crops])
        pages.append(img)
        rows.append(bands)
    blank = {"tries": 1} if engine == "ocrmac" else {}  # a tile of small digits can be blank
    try:
        return _readings(engine, ocr_pages(engine, pages, tmp, **blank), rows)
    except Exception as e:  # noqa: BLE001 - an engine missing or failing is skipped
        logger.warning("%s did not read the chart values: %s", engine, e)
        return None


def read(charts: list[list[Any]], settings: Any) -> pd.DataFrame:
    """The voted numbers of every crop (RGB pixels): chart index, box, token, x in the crop.

    Raises TooFewReadings when fewer engines read than the vote needs.
    """
    from ._registry import lab_families
    from .vote import TooFewReadings, _family, default_min_agree, vote

    with tempfile.TemporaryDirectory() as tmp, ThreadPoolExecutor() as pool:
        jobs = [
            pool.submit(_engine, e, charts, settings.crop.get(e, "color"), Path(tmp))
            for e in settings.engines
        ]
        got = {e: j.result() for e, j in zip(settings.engines, jobs, strict=True)}
    readers = [e for e, found in got.items() if found]
    families = lab_families(readers, settings.families)
    voters = len(set(map(_family(families), readers)))  # one vote for each lab
    need = settings.min_agree or default_min_agree(voters, bool(families))
    if voters < need:
        raise TooFewReadings(
            f"{voters} independent OCR readings ({', '.join(readers)}); need {need}"
        )
    found = _slots(pd.DataFrame([r for rows in got.values() if rows for r in rows]))
    return vote(found, key=["chart", "box", "token"], min_agree=need, families=families or None)
