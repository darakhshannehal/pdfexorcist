"""Engine registry."""

import subprocess
from collections.abc import Callable, Iterator
from pathlib import Path

from .rows import Page

Extractor = Callable[[Path], Iterator[Page]]
EXTRACTORS: dict[str, Extractor] = {}
DEFAULTS: list[str] = []
IN_PROCESS: set[str] = set()  # engines --jobs keeps in the calling process
OCR_DPI = 300
LABS = {"datalab": ["indra", "chandra"]}  # one lab's models share misreads; --ocr runs the first


def lab_families(names: list[str], families: dict[str, list[str]] | None) -> dict[str, list[str]]:
    """families, plus a family for each lab with two or more engines in names and in no family."""
    given = families or {}
    taken = {m for ms in given.values() for m in ms}
    labs = {f: ms for f, ms in LABS.items() if sum(m in names and m not in taken for m in ms) > 1}
    return {**labs, **given}


def one_per_lab(names: list[str]) -> list[str]:
    """names, with only the first engine of each lab."""
    later = {m for ms in LABS.values() for m in [m for m in ms if m in names][1:]}
    return [n for n in names if n not in later]


def register(
    name: str, default: bool = True, in_process: bool = False
) -> Callable[[Extractor], Extractor]:
    """Add an extractor under name.

    Args:
        name: The engine's name in methods and --engines.
        default: Run it when no engines are named.
        in_process: Never read in a worker process (a model held on the GPU).
    """

    def deco(fn: Extractor) -> Extractor:
        EXTRACTORS[name] = fn
        if default:
            DEFAULTS.append(name)
        if in_process:
            IN_PROCESS.add(name)
        return fn

    return deco


def tesseract_words(png: bytes, psm: int = 6) -> list[tuple[int, int, int, int, str]]:
    """Tesseract words of a PNG: (left, top, width, height, text) in pixels."""
    tsv = subprocess.run(
        ["tesseract", "stdin", "stdout", "--psm", str(psm), "tsv"],
        input=png,
        capture_output=True,
        check=True,
    ).stdout.decode()
    out = []
    for row in tsv.splitlines()[1:]:
        f = row.split("\t")
        if len(f) == 12 and f[0] == "5" and f[11].strip():
            out.append((int(f[6]), int(f[7]), int(f[8]), int(f[9]), f[11].strip()))
    return out
