"""Pages with /Rotate 90 (IMD Climatological Normals 1961-1990, Abu)."""

from pathlib import Path

import pytest

from pdfexorcist.extractors import EXTRACTORS

PDF = Path(__file__).parent / "fixtures" / "imd" / "imd_1961_1990_abu_p106-107.pdf"
JAN_II = ["882.5", "16.7", "9.7", "1965", "1986", "38", "7.1", "0.9", "0.5", "1940", "1888"]


def _jan_ii(engine: str) -> list:
    """Cells of page 1's JAN II row."""
    lines = next(iter(EXTRACTORS[engine](PDF)))[1]
    return next(ln[2:] for ln in lines if [t for _, t in ln[:2]] == ["JAN", "II"])


@pytest.mark.parametrize("engine", ["pymupdf", "pdfium"])
def test_engine_reads_rotated_page_upright_with_true_x(engine):
    ref = _jan_ii("pdfplumber")
    got = _jan_ii(engine)
    assert [t for _, t in got] == [t for _, t in ref] == JAN_II
    assert all(abs(a - b) < 3 for (a, _), (b, _) in zip(got, ref, strict=True))
