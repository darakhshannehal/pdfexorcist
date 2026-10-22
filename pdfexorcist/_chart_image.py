"""Charts pasted as images: values printed in colored boxes, read by OCR engines and voted."""

import difflib
import io
import logging
import math
import re
import tempfile
from pathlib import Path
from typing import Any, NamedTuple

from ._chart_legend import series_colors
from ._chart_ocr import boxed_cells, ocr_pages, read
from ._chart_settings import MONTHS, ChartSettings
from .charts import ChartError, Word, _number, _rows, _y_axis, has_letters, heading

logger = logging.getLogger(__name__)

MIN_PT = (100, 60)  # a smaller image is no chart
PAGE_SHARE = 0.8  # an image over more of the page is a background
COLORED = 0.002  # a chart has at least this share of saturated pixels
LAYOUT_SCALE = 2  # chart images are enlarged this much for the layout OCR
OFF_LINE = "value off its line"


class Row(NamedTuple):
    page: int
    chart: int
    title: str
    series: str
    category: str
    value: float | None
    status: str  # verified or unresolved, by the OCR vote
    votes: str
    line_value: float | None  # the series line at this category, by the y axis
    failed: str


COLUMNS = list(Row._fields)


class Chart(NamedTuple):
    page: int
    chart: int  # its number on the page
    title: str
    pixels: Any  # RGB numpy array


class Cell(NamedTuple):
    """Where one value (or several, left to right) is printed in a chart picture."""

    series: str
    category: str | None  # None: matched to the category labels by x
    box: tuple[int, int, int, int]  # x0, y0, x1, y1 in the picture's pixels


class Plan(NamedTuple):
    chart: Chart
    words: list[Word]
    colors: dict[str, tuple]
    cats: list[tuple[float, str]]
    text: Any  # bool per pixel: the box of a word with letters (no value box there)
    cells: list[Cell]


def chart_images(doc: Any, pages: list[int], settings: ChartSettings) -> list[Chart]:
    """The pictures on the pages that can be charts: large, colored and not a background."""
    import numpy as np
    from PIL import Image

    out = []
    for no in pages:
        page = doc[no - 1]
        area, words, n = page.rect.width * page.rect.height, None, 1
        for item in page.get_images(full=True):
            try:
                box = page.get_image_bbox(item)
            except ValueError:  # an image the page does not show
                continue
            small = box.is_infinite or box.width < MIN_PT[0] or box.height < MIN_PT[1]
            if small or box.width * box.height > PAGE_SHARE * area:
                continue
            raw = Image.open(io.BytesIO(doc.extract_image(item[0])["image"])).convert("RGB")
            if (np.array(raw.convert("HSV"))[..., 1] > 80).mean() < COLORED:
                continue
            words = words or [Word(*w[:5]) for w in page.get_text("words")]
            title = heading(words, box)
            if not settings.title or re.search(settings.title, title):
                out.append(Chart(no, n, title, np.array(raw)))
                n += 1
    return out


def layout(charts: list[Chart], engines: tuple[str, ...]) -> list[list[Word]]:
    """The words of each chart picture, in its pixels, from the first engine that reads them."""
    try:
        import cv2
    except ImportError:
        raise ChartError("charts in pictures need OpenCV and an OCR engine") from None

    k = LAYOUT_SCALE
    grays = [
        cv2.resize(cv2.cvtColor(c.pixels, cv2.COLOR_RGB2GRAY), None, fx=k, fy=k) for c in charts
    ]
    with tempfile.TemporaryDirectory() as tmp:
        for engine in engines:
            try:
                pages = ocr_pages(engine, grays, Path(tmp))
            except Exception as e:  # noqa: BLE001 - try the next engine
                logger.info("%s did not read the chart layout: %s", engine, e)
                continue
            return [
                [
                    Word(b[0] / k, b[1] / k, b[2] / k, b[3] / k, t)
                    for b, t in boxed_cells(pages.get(i, []))
                ]
                for i in range(1, len(charts) + 1)
            ]
    raise ChartError("charts in pictures need an OCR engine (pdfexorcist engines)")


def categories(words: list[Word], settings: ChartSettings, width: int) -> list[tuple[float, str]]:
    """(x, label) of each category; a missed label is placed by its evenly spaced neighbours."""
    import numpy as np

    names = list(settings.categories or MONTHS)
    best: list[tuple[int, float]] = []  # (label index, x)
    for row in _rows([w for w in words if _number(w.text) is None]):
        near = [(difflib.get_close_matches(w.text, names, n=1, cutoff=0.5), w) for w in row]
        hits = [(names.index(n[0]), (w.x0 + w.x1) / 2) for n, w in near if n]
        best = max(best, hits, key=len)
    if len(best) < 3:
        raise ChartError("no category labels: set [charts] categories")
    idx, xs = zip(*sorted(best), strict=True)
    slope, at0 = np.polyfit(idx, xs, 1)
    if slope <= 0:
        raise ChartError("the category labels are not left to right")
    return [(at0 + slope * i, n) for i, n in enumerate(names) if 0 <= at0 + slope * i <= width]


def excel_cells(chart: Chart, colors: dict, text: Any, settings: ChartSettings) -> list[Cell]:
    """The built-in cells: the solid blocks of each series color (Excel data labels).

    A series whose boxes are not in its line color takes the commonest fill no series has.
    """
    import numpy as np

    px = chart.pixels.astype(int)
    out = []
    for name, rgb in colors.items():
        out += [Cell(name, None, b) for b in _blocks(px, rgb, text, settings)]
    for name in [n for n in colors if all(c.series != n for c in out)]:
        taken = np.zeros(px.shape[:2], dtype=bool)
        for x0, y0, x1, y1 in (c.box for c in out):
            taken[y0:y1, x0:x1] = True
        fill = _spare_fill(px, taken | text, settings)
        if fill is not None:
            out += [Cell(name, None, b) for b in _blocks(px, fill, text, settings)]
    return out


def _blocks(px: Any, rgb: tuple, text: Any, settings: ChartSettings) -> list[tuple]:
    """(x0, y0, x1, y1) of each block of color rgb the size of a value box, clear of text."""
    import cv2
    import numpy as np

    low, high = settings.box_height
    tol = min(settings.color_distance, 0.5 * math.dist(rgb, (255, 255, 255)))  # not white
    m = cv2.morphologyEx(
        _near(px, rgb, tol).astype(np.uint8) * 255, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8)
    )
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, _kernel(settings))
    n, _, stats, _ = cv2.connectedComponentsWithStats(m)
    return [
        (int(x), int(y), int(x + w), int(y + h))
        for x, y, w, h, filled in stats[1:n]
        if low <= h <= high
        and w >= 0.6 * h  # a box of one digit is taller than wide
        and filled > 0.6 * w * h
        and not text[y : y + h, x : x + w].any()
    ]


def _near(px: Any, rgb: tuple, tol: float) -> Any:
    """True for each pixel within tol of the color rgb."""
    import numpy as np

    return np.linalg.norm(px - np.array(rgb), axis=2) < tol


def _kernel(settings: ChartSettings) -> Any:
    """An opening that removes lines and markers and keeps value boxes."""
    import numpy as np

    k = max(3, min(11, settings.box_height[0] - 1))
    return np.ones((k, k), np.uint8)


def _spare_fill(px: Any, taken: Any, settings: ChartSettings) -> tuple | None:
    """The commonest color of solid, non-white blocks outside taken, or None."""
    from collections import Counter

    import cv2
    import numpy as np

    ink = (255 - px).max(axis=2) > 25  # not white
    solid = cv2.morphologyEx(ink.astype(np.uint8), cv2.MORPH_OPEN, _kernel(settings)) > 0
    solid &= ~taken
    if solid.sum() < settings.box_height[0] ** 2 * 4:
        return None
    (color, _), *_ = Counter(map(tuple, (px[solid] // 16).tolist())).most_common(1)
    return tuple(int(v) * 16 + 8 for v in color)


def match(points: list[float], cats: list[tuple[float, str]]) -> list[str | None]:
    """The category of each x, left to right: in order, the nearest in sum.

    A point may be left out (None) at the cost of one category spacing: a stray box or token.
    """
    n, m = len(points), len(cats)
    skip = (cats[-1][0] - cats[0][0]) / max(m - 1, 1) if m else 0.0
    inf = float("inf")
    cost = [[inf] * (m + 1) for _ in range(n + 1)]  # i points into j categories
    move = [[""] * (m + 1) for _ in range(n + 1)]
    cost[0] = [0.0] * (m + 1)
    for i in range(1, n + 1):
        cost[i][0], move[i][0] = cost[i - 1][0] + skip, "drop"
        for j in range(1, m + 1):
            cost[i][j], move[i][j] = min(
                (cost[i][j - 1], "unused"),
                (cost[i - 1][j - 1] + abs(points[i - 1] - cats[j - 1][0]), "take"),
                (cost[i - 1][j] + skip, "drop"),
            )
    names: list[str | None] = []
    i, j = n, m
    while i:
        if move[i][j] == "unused":
            j -= 1
        else:
            names.append(cats[j - 1][1] if move[i][j] == "take" else None)
            i, j = i - 1, j - (move[i][j] == "take")
    return names[::-1]


def line_values(plan: Plan, settings: ChartSettings) -> tuple[dict, float]:
    """(series, category) -> the line's value there, by the y axis; and the axis label span."""
    import numpy as np

    if not plan.cats:
        return {}, 0.0
    left = min(x for x, _ in plan.cats) - 5
    ticks = [w for w in plan.words if _number(w.text) is not None and w.x1 < left]
    try:
        a, b = _y_axis(ticks, [])
    except (ChartError, ValueError):
        return {}, 0.0
    labels = [_number(w.text) or 0.0 for w in ticks]
    px = plan.chart.pixels.astype(int)
    covered = np.zeros(px.shape[:2], dtype=bool)
    for x0, y0, x1, y1 in (c.box for c in plan.cells):
        covered[max(0, y0 - 3) : y1 + 3, max(0, x0 - 3) : x1 + 3] = True
    out = {}
    for name, rgb in plan.colors.items():
        line = _near(px, rgb, settings.color_distance) & ~covered & ~plan.text
        for x, cat in plan.cats:
            ys = np.nonzero(line[:, max(0, int(x) - 2) : int(x) + 3].any(axis=1))[0]
            if len(ys):
                out[(name, cat)] = a + b * float(np.median(ys))
    return out, max(labels) - min(labels)


def _text(words: list[Word], shape: tuple) -> Any:
    """True for each pixel under a word with letters: titles, labels and the legend."""
    import numpy as np

    mask = np.zeros(shape[:2], dtype=bool)
    for w in words:
        if has_letters(w.text):
            mask[max(0, int(w.y0)) : int(w.y1) + 1, max(0, int(w.x0)) : int(w.x1) + 1] = True
    return mask


def _plan(c: Chart, words: list[Word], settings: ChartSettings) -> Plan | str | None:
    """The chart's plan, why it cannot be read, or None for a picture that is no chart."""
    cats: list[tuple[float, str]] = []
    text = _text(words, c.pixels.shape)
    try:
        cats = categories(words, settings, c.pixels.shape[1])
    except ChartError as e:
        if settings.cells is None:  # numbers up its left side: a chart we cannot place
            axis = sum(_number(w.text) is not None for w in words if w.x1 < c.pixels.shape[1] / 4)
            return str(e) if axis >= 3 else None
    try:
        colors = series_colors(c.pixels, words, settings)
        if settings.cells is None:
            return Plan(c, words, colors, cats, text, excel_cells(c, colors, text, settings))
        from PIL import Image

        found = settings.cells(Image.fromarray(c.pixels), words, settings)
        return Plan(c, words, colors, cats, text, [Cell(*x) for x in found])
    except ChartError as e:
        return str(e)


def image_charts(
    doc: Any, pages: list[int], settings: ChartSettings
) -> tuple[list[Row], list, list[str]]:
    """Rows for the chart pictures on the pages, the charts left out, and notes for the document."""
    from .vote import TooFewReadings

    charts = chart_images(doc, pages, settings)
    if not charts:
        return [], [], []
    try:
        texts = layout(charts, settings.engines)
    except ChartError as e:
        return [], [], [str(e)]
    plans: list[Plan] = []
    skipped: list[tuple] = []
    for c, words in zip(charts, texts, strict=True):
        got = _plan(c, words, settings)
        if isinstance(got, str):
            skipped.append((c.page, c.chart, got))
        elif got is not None and not got.cells:
            skipped.append((c.page, c.chart, "no value boxes: set [charts] cells to find them"))
        elif got is not None:
            plans.append(got)
    if not plans:
        return [], skipped, []
    crops = [
        [p.chart.pixels[y0:y1, x0:x1] for x0, y0, x1, y1 in (c.box for c in p.cells)] for p in plans
    ]
    try:
        voted = read(crops, settings)
    except TooFewReadings as e:
        why = f"{e} (set [engines] min_agree)"
        return [], skipped + [(p.chart.page, p.chart.chart, why) for p in plans], []
    rows: list[Row] = []
    for p, mine in zip(plans, _by_chart(voted, len(plans)), strict=True):
        try:
            rows += _rows_of(p, mine, settings)
        except ChartError as e:  # noqa: PERF203 - a chart that fails is skipped alone
            skipped.append((p.chart.page, p.chart.chart, str(e)))
    return rows, skipped, []


def _by_chart(voted: Any, n: int) -> list[dict]:
    """For each chart index: box -> its voted tokens, left to right."""
    out: list[dict] = [{} for _ in range(n)]
    ordered = voted.sort_values(["chart", "box", "token"])
    for (chart, box), g in ordered.groupby(["chart", "box"], sort=False):
        out[int(chart)][int(box)] = list(g.itertuples())
    return out


def _rows_of(p: Plan, voted: dict, settings: ChartSettings) -> list[Row]:
    """Each voted value at its category beside the line's value; a value missing is unresolved."""
    lines, span = line_values(p, settings)
    c, rows = p.chart, []
    for name in p.colors:
        points = sorted(  # (x, category or None, voted token), left to right
            ((cell.box[0] + r.x, cell.category, r) for b, cell in enumerate(p.cells)
             if cell.series == name for r in voted.get(b, [])),
            key=lambda t: t[0],
        )  # fmt: skip
        named = iter(match([x for x, cat, _ in points if cat is None], p.cats))
        at = {k: r for _, cat, r in points if (k := cat or next(named)) is not None}
        for cat in [k for _, k in p.cats] or list(at):
            line, r = lines.get((name, cat)), at.get(cat)
            if r is None and line is None:
                continue
            num = float(r.value) if r is not None and r.value else None
            status, votes = (r.status, r.votes) if r is not None else ("unresolved", "no value box")
            off = (
                num is not None
                and line is not None
                and abs(num - line) > settings.line_tolerance * span
            )
            rows.append(
                Row(
                    c.page,
                    c.chart,
                    c.title,
                    name,
                    cat,
                    num,
                    status,
                    votes,
                    line,
                    OFF_LINE if off else "",
                )
            )
    return rows
