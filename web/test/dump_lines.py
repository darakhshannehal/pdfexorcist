"""Every text engine's lines on every fixture, as JSON; parity.mjs compares native and Pyodide."""

import json
import sys
from pathlib import Path

from pdfexorcist.extractors import EXTRACTORS

# need native binaries or models Pyodide lacks; every other engine must match native
NATIVE_ONLY = {"tabula", "tesseract", "doctr", "indra", "paddleocr", "ocrmac", "chandra", "glmocr"}


def main(root: Path) -> None:
    out = {}
    for pdf in sorted((root / "tests" / "fixtures").rglob("*.pdf")):
        name = str(pdf.relative_to(root))
        for engine in (e for e in EXTRACTORS if e not in NATIVE_ONLY):
            try:
                pages = [
                    [p, [[[round(x, 3), t] for x, t in ln] for ln in lines]]
                    for p, lines in EXTRACTORS[engine](pdf)
                ]
            except Exception as e:  # noqa: BLE001 - compared like any output
                pages = type(e).__name__  # messages differ between CPython and Pyodide
            out[f"{engine} {name}"] = pages
    json.dump(out, sys.stdout, sort_keys=True)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
