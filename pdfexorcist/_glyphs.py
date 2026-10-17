"""Give Type3 fonts that lack a Unicode map one, read from their glyphs by OCR."""

import bisect
import hashlib
import logging
import re
import shutil
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ._prepare import save_copy
from ._registry import tesseract_words
from .rows import is_value

logger = logging.getLogger(__name__)

ZOOM = 4  # page render scale for OCR (288 dpi)
MIN_SHARE = 0.7  # a glyph's top reading needs this share of its votes
MAX_BAD_NUMBERS = 0.02  # share of number-like tokens that may fail to parse
MAX_BOX = 3  # a d1 box this many times taller than its drawing is refitted
D1 = re.compile(rb"^\s*(\S+\s+\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+d1")
BLANK = " "  # a code with no drawing (.notdef, empty char proc) is a space


class GlyphMapError(ValueError):
    """A Type3 glyph could not be read with confidence."""


@dataclass(frozen=True)
class Glyph:
    """One glyph's reading: its char proc, the text it maps to, and the evidence."""

    text: str
    share: float
    source: str  # "words" (OCR of whole words), "glyph" (OCR of the glyph alone), "blank"


Fonts = dict[int, dict[int, str]]  # font xref -> code -> glyph key


def _bare_type3(doc: Any) -> Fonts:
    """Type3 fonts with no ToUnicode whose glyph names map to no character."""
    import pymupdf

    out: Fonts = {}
    for xref in {f[0] for page in doc for f in page.get_fonts() if f[2] == "Type3"}:
        if doc.xref_get_key(xref, "ToUnicode")[0] != "null":
            continue
        names = _names(doc, xref)
        if any(pymupdf.glyph_name_to_unicode(n) not in (0, 0xFFFD) for n in names.values()):
            continue  # standard names: engines map them already
        procs = _procs(doc, xref)
        out[xref] = {code: _glyph_key(doc, procs.get(name)) for code, name in names.items()}
    return out


def _names(doc: Any, font: int) -> dict[int, str]:
    """Code -> glyph name from the font's /Encoding /Differences."""
    kind, val = doc.xref_get_key(font, "Encoding")
    text = doc.xref_object(int(val.split()[0])) if kind == "xref" else val
    m = re.search(r"/Differences\s*\[(.*?)\]", text, re.S)
    out, code = {}, 0
    for tok in re.findall(r"\d+|/[^\s/\[\]]+", m.group(1) if m else ""):
        if tok.startswith("/"):
            out[code] = tok[1:]
            code += 1
        else:
            code = int(tok)
    return out


def _procs(doc: Any, font: int) -> dict[str, int]:
    """Glyph name -> char proc xref."""
    kind, val = doc.xref_get_key(font, "CharProcs")
    text = doc.xref_object(int(val.split()[0])) if kind == "xref" else val
    return {m.group(1): int(m.group(2)) for m in re.finditer(r"/(\S+)\s+(\d+)\s+0\s+R", text)}


_PAINT = re.compile(rb"(?<![^\s\]>)])(f\*?|F|S|s|B\*?|b\*?|Do|BI|sh)(?=\s|$)")


def _glyph_key(doc: Any, proc: int | None) -> str:
    """sha1 of a char proc's drawing; BLANK when it paints nothing (a space)."""
    body = _drawing(doc, proc)
    return hashlib.sha1(body).hexdigest() if _PAINT.search(body) else BLANK


def _drawing(doc: Any, proc: int | None) -> bytes:
    """A char proc's operators after its d0/d1 header."""
    if proc is None:
        return b""
    return re.sub(rb"^.*?\bd[01]\s", b"", doc.xref_stream(proc) or b"", count=1, flags=re.S)


def _ocr_words(png: bytes, psm: int = 6) -> list[tuple[tuple[float, ...], str]]:
    """Tesseract words of a page image: ((x0, y0, x1, y1) in points, text)."""
    out: list[tuple[tuple[float, ...], str]] = []
    for *box, text in tesseract_words(png, psm):
        x, y, w, h = (v / ZOOM for v in box)
        out.append(((x, y, x + w, y + h), text))
    return out


def _font_xref(span: dict, page_fonts: dict[str, int]) -> int | None:
    """The xref of a span's font; MuPDF names bare Type3 fonts "Type3 (<xref> 0 R)"."""
    if m := re.search(r"\((\d+) 0 R\)", span["font"]):
        return int(m.group(1))
    return page_fonts.get(span["font"])


def _page_votes(page: Any, fonts: Fonts, votes: defaultdict[str, Counter]) -> Counter:
    """Add each OCR word's letters as votes for the glyphs under it; count glyph uses."""
    import pymupdf

    page_fonts = {f[3]: f[0] for f in page.get_fonts()}
    chars = []  # (glyph key, origin x, origin y, size)
    for block in page.get_text("rawdict", flags=pymupdf.TEXTFLAGS_TEXT)["blocks"]:
        for line in block.get("lines", []):
            for span in line["spans"]:
                codes = fonts.get(_font_xref(span, page_fonts) or -1)
                if codes is None:
                    continue
                for c in span["chars"]:
                    key = codes.get(ord(c["c"]))
                    if key and key != BLANK:
                        chars.append((key, *c["origin"], span["size"]))
    used = Counter(k for k, *_ in chars)
    if not chars:
        return used
    chars.sort(key=lambda c: c[1])
    xs = [c[1] for c in chars]
    png = page.get_pixmap(matrix=pymupdf.Matrix(ZOOM, ZOOM), colorspace=pymupdf.csGRAY)
    for (x0, y0, x1, y1), text in _ocr_words(png.tobytes("png")):
        # glyph boxes of these fonts are unreliable; their origins sit on the baseline
        span = chars[bisect.bisect_left(xs, x0 - 1) : bisect.bisect_right(xs, x1)]
        under = [c for c in span if y0 <= c[2] <= y1 + 0.3 * c[3]]
        text = text.strip("|[]{}")  # OCR reads a table rule beside a word as "|" or "["
        if under and len(under) == len(text):
            for (key, *_), ch in zip(under, text, strict=True):
                votes[key][ch] += 1
    return used


def _alone(doc: Any, proc: int | None, cm: bytes) -> Any:
    """A 120 pt page with one char proc drawn under cm (caller closes it)."""
    import pymupdf

    one = pymupdf.open()
    page = one.new_page(width=120, height=120)
    xref = one.get_new_xref()
    one.update_object(xref, "<<>>")
    one.update_stream(xref, b"q " + cm + b" cm\n" + _drawing(doc, proc) + b"\nQ")
    one.xref_set_key(page.xref, "Contents", f"{xref} 0 R")
    return one


def _glyph_alone(doc: Any, font: int, code: int) -> str:
    """OCR one glyph drawn large on its own page."""
    import pymupdf

    proc = _procs(doc, font).get(_names(doc, font).get(code, ""))
    with _alone(doc, proc, b"80 0 0 80 20 20") as one:
        png = one[0].get_pixmap(dpi=144, colorspace=pymupdf.csGRAY).tobytes("png")
    words = _ocr_words(png, psm=10)
    return words[0][1] if len(words) == 1 and len(words[0][1]) == 1 else ""


def glyph_map(doc: Any, fonts: Fonts) -> dict[str, Glyph]:
    """Read every used glyph of the bare Type3 fonts; raise GlyphMapError when one is unclear."""
    votes: defaultdict[str, Counter] = defaultdict(Counter)
    used: Counter = Counter()
    for page in doc:
        used += _page_votes(page, fonts, votes)
    out: dict[str, Glyph] = {BLANK: Glyph(" ", 1.0, "blank")}
    unclear = []
    owner = {k: (f, c) for f, codes in fonts.items() for c, k in codes.items()}
    for key in used:
        if votes[key]:
            text, n = votes[key].most_common(1)[0]
            share = n / sum(votes[key].values())
            if share >= MIN_SHARE:
                out[key] = Glyph(text, share, "words")
                continue
            unclear.append(f"{key[:8]} read as {dict(votes[key])}")
            continue
        font, code = owner[key]
        if text := _glyph_alone(doc, font, code):
            out[key] = Glyph(text, 1.0, "glyph")
        else:
            unclear.append(f"{key[:8]} (code {code} of font {font}) unreadable")
    if unclear:
        raise GlyphMapError("Type3 glyphs read unclearly: " + "; ".join(unclear))
    return out


def _cmap(codes: dict[int, str]) -> bytes:
    """A ToUnicode CMap for one-byte codes."""
    items = sorted(codes.items())
    parts = []
    for i in range(0, len(items), 100):  # bfchar blocks hold at most 100 entries
        chunk = items[i : i + 100]
        lines = "\n".join(f"<{c:02X}> <{t.encode('utf-16-be').hex().upper()}>" for c, t in chunk)
        parts.append(f"{len(chunk)} beginbfchar\n{lines}\nendbfchar")
    return (
        "/CIDInit /ProcSet findresource begin\n12 dict begin\nbegincmap\n"
        "/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def\n"
        "/CMapName /pdfexorcist-type3 def\n/CMapType 2 def\n"
        "1 begincodespacerange\n<00> <FF>\nendcodespacerange\n"
        + "\n".join(parts)
        + "\nendcmap\nCMapName currentdict /CMap defineresource pop\nend\nend\n"
    ).encode()


def _ink(doc: Any, proc: int) -> tuple[float, float, float, float] | None:
    """The extent of a char proc's drawing in glyph space, or None when it draws nothing."""
    import pymupdf

    with _alone(doc, proc, b"1 0 0 1 0 0") as one:
        box = pymupdf.Rect()
        for path in one[0].get_drawings():
            box |= path["rect"]
    return None if box.is_empty else (box.x0, 120 - box.y1, box.x1, 120 - box.y0)


def _fit_glyph_boxes(doc: Any) -> int:
    """Fit d1 glyph boxes far taller than their drawing to it; return how many.

    PDFium sizes a Type3 glyph by its d1 box, so a bogus one spans many rows.
    """
    fitted = 0
    for xref in {f[0] for page in doc for f in page.get_fonts() if f[2] == "Type3"}:
        for proc in _procs(doc, xref).values():
            body = doc.xref_stream(proc) or b""
            m = D1.match(body)
            if not m or not (ink := _ink(doc, proc)):
                continue
            lly, ury = float(m.group(3)), float(m.group(5))
            if ury - lly <= MAX_BOX * (ink[3] - ink[1]):
                continue
            head = m.group(1) + b" %.4f %.4f %.4f %.4f d1" % ink
            doc.update_stream(proc, head + body[m.end() :])
            fitted += 1
    return fitted


def _bad_numbers(doc: Any) -> tuple[int, list[str]]:
    """Count number-like tokens; list those that do not parse as a value."""
    toks = [t for page in doc for t in page.get_text().split() if re.fullmatch(r"[\d.,\-]+", t)]
    return len(toks), [t for t in toks if any(c.isdigit() for c in t) and not is_value(t)]


def decode_type3(pdf: Path, out_dir: Path) -> Path:
    """Copy of pdf with its Type3 fonts made readable, or pdf itself.

    Glyph boxes far taller than their drawing are fitted to it. Fonts without a
    Unicode map get one read by OCR, so every text engine reads the text and the
    normal vote runs. Each glyph
    is read from OCR of the words it is part of (once per char proc, so fonts
    sharing a glyph share its reading), or of the glyph alone when no word
    covers it.

    Raises:
        GlyphMapError: a glyph's readings disagree, or the decoded numbers do not parse.
    """
    import pymupdf

    with pymupdf.open(pdf) as doc:
        fitted = _fit_glyph_boxes(doc)
        if fitted:
            logger.info("%d Type3 glyph boxes fitted to their drawing", fitted)
        fonts = _bare_type3(doc)
        if fonts and not shutil.which("tesseract"):
            logger.warning(
                "%d Type3 fonts have no Unicode map; decoding them needs tesseract, "
                "so the text engines read control codes",
                len(fonts),
            )
            fonts = {}
        if not fonts:
            return save_copy(doc, out_dir, pdf.name) if fitted else pdf
        glyphs = glyph_map(doc, fonts)
        for font, codes in fonts.items():
            known = {c: glyphs[k].text for c, k in codes.items() if k in glyphs}
            xref = doc.get_new_xref()
            doc.update_object(xref, "<<>>")
            doc.update_stream(xref, _cmap(known))
            doc.xref_set_key(font, "ToUnicode", f"{xref} 0 R")
        n, bad = _bad_numbers(doc)
        if bad and len(bad) > MAX_BAD_NUMBERS * n:
            raise GlyphMapError(f"{len(bad)} of {n} decoded numbers do not parse: {bad[:10]}")
        by_source = Counter(g.source for g in glyphs.values() if g.source != "blank")
        low = min((g.share for g in glyphs.values()), default=1.0)
        logger.warning(
            "%d Type3 fonts had no Unicode map; %d glyphs read by OCR (%s), "
            "lowest agreement %.0f%%",
            len(fonts),
            sum(by_source.values()),
            ", ".join(f"{n} from {s}" for s, n in by_source.items()),
            100 * low,
        )
        return save_copy(doc, out_dir, pdf.name)
