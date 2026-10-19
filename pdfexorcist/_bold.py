"""Undo fake bold: text drawn several times a fraction of a point apart."""

import re
from collections.abc import Callable, Sequence

from .cells import BoxCell

_RUNS = re.compile(r"(.)\1*")
COPY_PT = 1.5  # copies of a fake-bold word lie closer than this


def drop_copies(boxes: list[tuple]) -> list[tuple]:
    """Keep one of each (x0, x1, top, bottom, text) word drawn again within COPY_PT."""
    kept: dict[tuple, list[tuple]] = {}  # (text, x0, top) on a COPY_PT grid -> words
    out = []
    for b in boxes:
        gx, gy = int(b[0] // COPY_PT), int(b[3] // COPY_PT)
        near = (
            k
            for dx in (-1, 0, 1)
            for dy in (-1, 0, 1)
            for k in kept.get((b[4], gx + dx, gy + dy), ())
        )
        if any(abs(k[0] - b[0]) < COPY_PT and abs(k[3] - b[3]) < COPY_PT for k in near):
            continue
        kept.setdefault((b[4], gx, gy), []).append(b)
        out.append(b)
    return out


def _once(text: str, k: int) -> str | None:
    """text drawn k times as one string, undone; None when it is not.

    Engines read k copies as the words repeated ("Goa Goa"), each word repeated
    ("Andhra Andhra Pradesh Pradesh"), the text glued k times ("388388388388"), or
    each glyph repeated ("GGooaa", "1100" for "10").
    """
    words = text.split()
    n = len(words)
    if not n:
        return None
    if n % k == 0 and words == words[: n // k] * k:
        return " ".join(words[: n // k])
    if n % k == 0 and all(len(set(words[i : i + k])) == 1 for i in range(0, n, k)):
        return " ".join(words[::k])
    glued = "".join(words)
    if len(glued) % k == 0 and glued == glued[: len(glued) // k] * k:
        return glued[: len(glued) // k]
    fixed = []
    for w in words:
        runs = [m.group() for m in _RUNS.finditer(w)]
        if any(len(r) % k for r in runs):
            return None
        fixed.append("".join(r[: len(r) // k] for r in runs))
    return " ".join(fixed)


def _letters(text: str) -> str:
    return re.sub(r"[^A-Za-z]", "", text)


def bold_k(label: str) -> int:
    """How many times a row label's letters were drawn (1 when it is plain)."""
    for k in (4, 3, 2):
        once = _once(label, k)
        # every letter repeats k times, and three letters are left ("GGooaa", not "AA")
        n = len(_letters(once or ""))
        if once is not None and n >= 3 and len(_letters(label)) == k * n:
            return k
    return 1


def debold_line(cells: Sequence, is_value: Callable[[str], bool]) -> list:
    """Undo fake bold on a line of (x, text) cells read without glyph boxes.

    k comes from the label (the cells before the first value): it is drawn k
    times exactly when every label letter is. Only then are the values undone
    by the same k, so a plain row's repeated digits ("11110") stay as printed.
    """
    label = []
    for c in cells:
        if all(is_value(t) for t in c[1].split()):
            break
        label.append(c[1])
    k = bold_k(" ".join(label))
    if k == 1:
        return list(cells)
    out = []
    for c in cells:
        once = _once(c[1], k)
        text = c[1] if once is None else once
        out.append(BoxCell(c[0], text, getattr(c, "box", None)))
    return out


def one_value(text: str, is_value: Callable[[str], bool]) -> str:
    """A cell of one value drawn several times ("366 366366"), read once.

    For engines that read a table cell's text from overprinted glyphs (camelot):
    each cell can repeat a different number of times. Needs two tokens or more,
    so a printed 366366 stays.
    """
    # also merges equal values of merged columns ("0 0"); that engine loses its vote
    toks = text.split()
    if len(toks) < 2 or not all(is_value(t) for t in toks):
        return text
    glued = "".join(toks)
    unit = toks[0]
    return unit if glued == unit * (len(glued) // len(unit)) else text
