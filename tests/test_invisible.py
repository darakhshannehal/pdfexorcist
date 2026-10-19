"""Text drawn but not visible is dropped before the engines read the page."""

from pathlib import Path

import pymupdf
import pytest

from pdfexorcist._invisible import drop_invisible
from pdfexorcist.extractors import EXTRACTORS

WHITE, BLACK, GREY = (1, 1, 1), (0, 0, 0), (0.94, 0.94, 0.94)


def _page(path: Path) -> Path:
    """One page: each line is a case, named by its first word."""
    doc = pymupdf.open()
    page = doc.new_page(width=400, height=300)
    page.insert_text((20, 40), "Visible 11", color=BLACK)
    page.insert_text((20, 70), "Whiteonwhite 22", color=WHITE)
    page.draw_rect(pymupdf.Rect(15, 85, 200, 110), color=None, fill=BLACK)
    page.insert_text((20, 100), "Header 33", color=WHITE)
    page.insert_text((20, 130), "Hiddenmode 44", render_mode=3)
    page.insert_text((20, 160), "Transparent 55", color=BLACK, fill_opacity=0)
    # IFCT 2017 p67: a small white "Z." inside the box of a black "E" on a light grey row
    page.draw_rect(pymupdf.Rect(15, 175, 300, 200), color=None, fill=GREY)
    page.insert_text((20, 190), "Eggs 66", color=BLACK, fontsize=11)
    page.insert_text((20.6, 188), "Z.", color=WHITE, fontsize=5)
    # an OCR layer: render mode 3 over a scan stays
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 40, 10), False)
    pix.set_rect(pix.irect, (200, 200, 200))
    page.insert_image(pymupdf.Rect(15, 215, 215, 240), pixmap=pix, keep_proportion=False)
    page.insert_text((20, 230), "Scanned 77", render_mode=3)
    doc.save(path)
    return path


@pytest.mark.parametrize("engine", ["pdfplumber", "pymupdf", "pdfium", "pdftotext"])
def test_invisible_text_is_not_read(tmp_path: Path, engine: str) -> None:
    pdf = drop_invisible(_page(tmp_path / "page.pdf"), tmp_path / "visible")
    ((_, lines),) = EXTRACTORS[engine](pdf)
    text = [" ".join(t for _, t in line) for line in lines if line]
    assert text == ["Visible 11", "Header 33", "Eggs 66", "Scanned 77"]


def test_a_page_without_hidden_text_is_not_copied(tmp_path: Path) -> None:
    doc = pymupdf.open()
    doc.new_page().insert_text((20, 40), "Visible 11")
    doc.save(tmp_path / "plain.pdf")
    assert drop_invisible(tmp_path / "plain.pdf", tmp_path / "out") == tmp_path / "plain.pdf"
