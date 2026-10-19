"""Shipped recipes, and recipe suggest."""

import fnmatch
import json
import shutil
import sys
from pathlib import Path

import pytest
from cli_helpers import make_pdf, run

from pdfexorcist import recipe
from pdfexorcist._shipped import (
    find_shipped,
    resolve_recipe,
    shipped_dir,
)
from pdfexorcist._suggest import build_index, load_index

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - Python 3.10
    import tomli as tomllib

ROOT = Path(__file__).parent.parent
FIXTURES = Path(__file__).parent / "fixtures"

pytestmark = pytest.mark.usefixtures("wide_console")


@pytest.mark.skipif(not (ROOT / "pyproject.toml").exists(), reason="no pyproject.toml (Pyodide)")
def test_wheel_ships_every_recipe_file():
    """Pin packaging that covers every file in pdfexorcist/recipes/: parsers and data."""
    conf = tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]["setuptools"]
    assert "pdfexorcist.*" in conf["packages"]["find"]["include"]  # the parsers
    data = conf["package-data"]["*"]
    files = [
        p.name
        for p in (ROOT / "pdfexorcist" / "recipes").rglob("*")
        if p.is_file() and "__pycache__" not in p.parts
    ]
    assert files
    assert [
        f for f in files if not f.endswith(".py") and not any(fnmatch.fnmatch(f, g) for g in data)
    ] == []


def test_find_shipped_by_name():
    """Pin short names: a folder's recipe.toml, a named file, and one at the top."""

    def found(name: str) -> str | None:
        p = find_shipped(name)
        return p and p.relative_to(shipped_dir()).as_posix()

    assert found("cpcb_aqi") == "cpcb_aqi/recipe.toml"
    assert found("mccd/table9.toml") == "mccd/table9.toml"
    assert found("crime_in_india") == "crime_in_india.toml"
    assert found("nope") is None
    assert (
        recipe.load(resolve_recipe(Path("karnataka_idsp"))).name == "Karnataka IDSP weekly report"
    )
    assert resolve_recipe(Path("missing.toml")) == Path("missing.toml")


def test_index_is_current():
    """Pin the shipped index to a fresh one: recipes, samples, pages and the fingerprint code.
    An OCR'd sample's fingerprint depends on the tesseract build, so only its files are pinned."""
    stored = load_index()
    fresh = json.loads(json.dumps(build_index(ROOT / "pdfexorcist" / "recipes")["entries"]))
    assert len(fresh) == len(stored), "rebuild: python -m pdfexorcist._suggest"

    def pinned(entries: list) -> list:
        ocr = ("words", "shapes", "xs", "ocr")
        return [
            {k: v for k, v in e.items() if not (s["ocr"] and k in ocr)}
            for e, s in zip(entries, stored, strict=True)
        ]

    assert pinned(stored) == pinned(fresh), "rebuild: python -m pdfexorcist._suggest"


@pytest.mark.parametrize(
    ("fixture", "best"),
    [
        ("cpcb/cpcb_aqi_2026-10-18_p1-2_14-15.pdf", "cpcb_aqi"),
        ("karnataka_idsp/karnataka_idsp_2026_week41.pdf", "karnataka_idsp"),
    ],
)
def test_suggest_finds_the_recipe(fixture: str, best: str) -> None:
    """Pin the fitting recipe first, read by its trial run."""
    r = run(["recipe", "suggest", str(FIXTURES / fixture), "--json"])
    assert r.exit_code == 0, r.output
    found = json.loads(r.stdout)["recipes"]
    assert found[0]["recipe"] == best and found[0]["fits"]
    assert found[0]["cells"] > 0 and found[0]["failed_checks"] == []
    assert [f["recipe"] for f in found if f["fits"]] == [best]


def test_suggest_without_a_fit(tmp_path: Path) -> None:
    """Pin the advice when no recipe reads a page without a table."""
    pdf = make_pdf(tmp_path / "letter.pdf", [[]], ["Dear reader, this page holds no table at all."])
    r = run(["recipe", "suggest", str(pdf)])
    assert r.exit_code == 0, r.output
    assert "No shipped recipe fits this PDF." in r.stdout
    assert f"pdfexorcist recipe new {pdf}" in r.stdout.replace("\n", "")


@pytest.mark.skipif(not shutil.which("tesseract"), reason="needs tesseract")
def test_suggest_on_a_photo() -> None:
    """Pin a photo matched by its OCR'd words: tried with an OCR engine, or naming the ones
    its recipe needs."""
    r = run(["recipe", "suggest", str(FIXTURES / "bmc" / "2026-07-28.jpg"), "--json"])
    assert r.exit_code == 0, r.output
    best = json.loads(r.stdout)["recipes"][0]
    assert best["recipe"] == "mybmc_lakes" and best["words"] > 0.5
    assert best["fits"] or (best["needs"] and not best["cells"])
