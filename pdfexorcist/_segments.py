"""Merge rules drawn as thousands of short pieces into whole lines."""

import logging
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from ._prepare import replace_each

logger = logging.getLogger(__name__)

MANY = 2000  # line pieces on a page before they are merged
HEAVY = 200_000  # content-stream bytes before a page's drawings are counted at all
GAP = 0.1  # pt between pieces of one rule
TOKEN = re.compile(
    rb"\((?:\\.|[^\\)])*\)|<<|>>|<[^>]*>|\[|\]|/[^\s/\[\]()<>{}%]+|[^\s/\[\]()<>{}%]+"
)
# a q ... Q group of only these draws nothing: path, clip, colour and other state operators
QUIET = {
    b"cm", b"m", b"l", b"c", b"v", b"y", b"h", b"re", b"W", b"W*", b"n", b"d", b"w", b"J",
    b"j", b"M", b"i", b"gs", b"G", b"g", b"RG", b"rg", b"K", b"k", b"CS", b"cs", b"SC",
    b"sc", b"SCN", b"scn", b"[", b"]",
}  # fmt: skip
PAINT = re.compile(rb"(?<![^\s])(?:f\*?|F|B\*?|b\*?|sh)(?![^\s])")  # fills: not rules alone


def drop_empty_groups(stream: bytes) -> bytes:
    """The content stream without q ... Q groups that draw nothing; as it is if it holds an
    inline image, whose data cannot be scanned as tokens."""
    frames: list[list] = []  # [start of q, draws nothing so far]
    cut: list[tuple[int, int]] = []
    for m in TOKEN.finditer(stream):
        tok = m.group()
        if tok == b"BI":
            return stream
        if tok == b"q":
            frames.append([m.start(), True])
        elif tok == b"Q" and frames:
            start, quiet = frames.pop()
            if quiet:
                while cut and cut[-1][0] > start:  # groups inside this one
                    cut.pop()
                cut.append((start, m.end()))
            elif frames:
                frames[-1][1] = False
        elif frames and not (tok in QUIET or tok[:1] in b"/-.0123456789"):
            frames[-1][1] = False
    out, at = [], 0
    for s, e in cut:
        out += [stream[at:s], b" "]
        at = e
    return b"".join([*out, stream[at:]])


def _rules(drawings: list[dict]) -> list[tuple[Any, Any, float, tuple]] | None:
    """Level and upright pieces merged into rules (from, to, width, colour); None when the
    page draws anything else."""
    import pymupdf

    runs: dict[tuple, list[list[float]]] = defaultdict(list)
    for d in drawings:
        if d.get("fill") is not None or d.get("dashes") not in (None, "[] 0"):
            return None
        width, colour = d.get("width") or 0.0, tuple(d.get("color") or (0.0, 0.0, 0.0))
        for item in d["items"]:
            if item[0] != "l":
                return None
            a, b = item[1], item[2]
            level = abs(a.y - b.y) < 0.01
            if not level and abs(a.x - b.x) >= 0.01:
                return None
            along, at = ((a.x, b.x), a.y) if level else ((a.y, b.y), a.x)
            runs[level, round(at, 2), width, colour].append(sorted(along))
    out = []
    for (level, at, width, colour), spans in runs.items():
        spans.sort()
        merged = [spans[0]]
        for s, e in spans[1:]:
            if s <= merged[-1][1] + GAP:
                merged[-1][1] = max(merged[-1][1], e)
            else:
                merged.append([s, e])
        for s, e in merged:
            ends = ((s, at), (e, at)) if level else ((at, s), (at, e))
            out.append((pymupdf.Point(ends[0]), pymupdf.Point(ends[1]), width, colour))
    return out


def _chars(page: Any) -> list[tuple]:
    return [
        (c["c"], *c["bbox"])
        for b in page.get_text("rawdict")["blocks"]
        for ln in b.get("lines", [])
        for s in ln["spans"]
        for c in s["chars"]
    ]


def _moved(before: list[tuple], after: list[tuple]) -> bool:
    """Whether any glyph changed or moved by more than a rounding step."""
    return len(after) != len(before) or any(
        a[0] != b[0] or max(abs(u - v) for u, v in zip(a[1:], b[1:], strict=True)) > 0.05
        for a, b in zip(before, after, strict=True)
    )


def _merged(doc: Any, page: Any) -> Any:
    """A one-page copy of page with its pieces drawn as whole rules, or None to keep it."""
    import pymupdf

    streams = [doc.xref_stream(x) or b"" for x in page.get_contents()]
    if page.rotation or sum(map(len, streams)) < HEAVY or any(PAINT.search(s) for s in streams):
        return None
    drawings = page.get_drawings()
    if sum(len(d["items"]) for d in drawings) < MANY or (rules := _rules(drawings)) is None:
        return None
    with pymupdf.open() as one:
        one.insert_pdf(doc, from_page=page.number, to_page=page.number)
        p = one[0]
        text = _chars(p)
        p.add_redact_annot(p.rect)
        # PDF_REDACT_IMAGE_NONE, PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED, PDF_REDACT_TEXT_NONE
        p.apply_redactions(images=0, graphics=2, text=1)
        if p.get_drawings() or _moved(text, _chars(p)):  # line art off the page stays
            return None
        for xref in p.get_contents():  # the clip paths each piece left behind
            one.update_stream(xref, drop_empty_groups(one.xref_stream(xref)))
        shape = p.new_shape()
        for a, b, width, colour in rules:
            shape.draw_line(a, b)
            shape.finish(width=width, color=colour, closePath=False)
        shape.commit()
        return pymupdf.open("pdf", one.tobytes(garbage=3, deflate=True))


def merge_segments(pdf: Path, out_dir: Path) -> Path:
    """Copy of pdf with rules drawn piece by piece redrawn whole, or pdf itself."""
    return replace_each(pdf, out_dir, _merged, "rules drawn in pieces redrawn whole")
