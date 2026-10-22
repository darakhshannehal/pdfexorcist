"""Apple Vision OCR in a subprocess."""

import io
import json
import sys
import time

from ocrmac import ocrmac
from PIL import Image

TRIES = 3  # Vision sometimes returns nothing while the GPU is busy with other work


def read(img: Image.Image, fast: bool = False, tries: int = TRIES) -> tuple[list, bool]:
    """Vision's reading of one image, and whether to read the next with "fast"."""
    found: list = []
    for attempt in range(0 if fast else tries):
        if attempt:
            time.sleep(1)
        if found := ocrmac.OCR(img, recognition_level="accurate").recognize():
            break
    if not found:  # a blank page stays empty either way
        found = ocrmac.OCR(img, recognition_level="fast").recognize()
        fast = fast or bool(found)
    return [[text, conf, list(box)] for text, conf, box in found], fast


def main() -> None:
    stdin = sys.stdin.buffer
    tries = int(sys.argv[1]) if len(sys.argv) > 1 else TRIES  # charts: a blank tile is common
    fast = False
    while len(head := stdin.read(4)) == 4:
        img = Image.open(io.BytesIO(stdin.read(int.from_bytes(head, "big"))))
        found, fast = read(img, fast, tries)
        sys.stdout.write(json.dumps(found) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
