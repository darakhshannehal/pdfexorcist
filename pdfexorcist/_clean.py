"""Clean a PDF before the engines read it."""

from pathlib import Path

from ._glyphs import decode_type3
from ._invisible import drop_invisible
from ._prepare import _pages, crop_pages, fit_page_boxes
from ._segments import merge_segments
from ._slanted import drop_slanted
from ._upright import upright_pages


def clean_pdf(pdf: Path, out_dir: Path, decode_fonts: bool = True, fit_boxes: bool = True) -> Path:
    """Redraw rules drawn in pieces whole, decode Type3 glyphs, fit page boxes, turn sideways
    pages upright, drop slanted and invisible text; each step writes a copy under out_dir."""
    pdf = merge_segments(pdf, out_dir / "rules")
    if decode_fonts:
        pdf = decode_type3(pdf, out_dir / "decoded")
    if fit_boxes:
        pdf = fit_page_boxes(pdf, out_dir / "fit")
    pdf = upright_pages(pdf, out_dir / "upright")
    pdf = drop_slanted(pdf, out_dir / "level")
    return drop_invisible(pdf, out_dir / "visible")


def cut(pdf: Path, pages: list[int] | None, area: tuple | None, out_dir: Path) -> Path:
    """The pages a run reads, cropped to area; a copy under out_dir when either is set."""
    pdf = _pages(pdf, pages, out_dir) if pages else pdf
    return crop_pages(pdf, out_dir / "area", area) if area else pdf


def prepare(
    pdf: Path, pages: list[int] | None, area: tuple | None, out_dir: Path, fit_boxes: bool = True
) -> Path:
    """cut, then clean_pdf: what the engines read in a run."""
    return clean_pdf(cut(pdf, pages, area, out_dir), out_dir, fit_boxes=fit_boxes)
