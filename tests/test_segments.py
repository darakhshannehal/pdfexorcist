"""Rules drawn as thousands of short pieces."""

from pathlib import Path

import pymupdf

from pdfexorcist._segments import MANY, drop_empty_groups, merge_segments


def _pieces_pdf(path: Path) -> Path:
    """A page with a word and one rule drawn as clipped 0.2 pt pieces, as some renderers do."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 100), "Bhatsa 929.20")
    clip = "0 0 m 0.2 0 l 0.2 1 l 0 1 l h W n"
    ops = [
        f"q 1 0 0 1 {72 + 0.2 * i:.1f} 700 cm {clip} 0 G 0.8 w 0 0 m 0.2 0 l S Q"
        for i in range(MANY + 500)
    ]
    xref = page.get_contents()[0]
    doc.update_stream(xref, doc.xref_stream(xref) + ("\n" + "\n".join(ops)).encode())
    doc.save(path)
    return path


def test_pieces_become_one_rule(tmp_path: Path) -> None:
    """Pin one redrawn rule, the text kept, and a far smaller page."""
    pdf = _pieces_pdf(tmp_path / "rules.pdf")
    out = merge_segments(pdf, tmp_path / "out")
    assert out != pdf
    with pymupdf.open(pdf) as before, pymupdf.open(out) as after:
        assert len(before[0].get_drawings()) > MANY
        rules = after[0].get_drawings()
        assert len(rules) == 1 and round(rules[0]["width"], 2) == 0.8
        assert after[0].get_text().strip() == before[0].get_text().strip() == "Bhatsa 929.20"
        r = rules[0]["rect"]
        assert (round(r.x0, 1), round(r.x1, 1)) == (72.0, round(72 + 0.2 * (MANY + 500), 1))


def test_a_light_page_is_kept(tmp_path: Path) -> None:
    doc = pymupdf.open()
    doc.new_page().draw_line((72, 700), (500, 700))
    doc.save(tmp_path / "one.pdf")
    assert merge_segments(tmp_path / "one.pdf", tmp_path / "out") == tmp_path / "one.pdf"


def test_drop_empty_groups() -> None:
    """Pin groups that draw nothing removed; text, painting and inline images kept."""
    s = b"q 1 0 0 1 2 3 cm 0 0 m 1 1 l h W n Q BT (a Q) Tj ET q q 0 0 m W n Q 0 0 m 5 5 l S Q"
    assert drop_empty_groups(s).split() == b"BT (a Q) Tj ET q 0 0 m 5 5 l S Q".split()
    image = b"q BI /W 1 ID xx EI Q"
    assert drop_empty_groups(image) == image
