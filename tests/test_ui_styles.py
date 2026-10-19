"""The console's colours: every style the CLI prints resolves in its theme."""

import re
from pathlib import Path

import pytest
from cli_helpers import run

import pdfexorcist
from pdfexorcist._cli_app import COMMON
from pdfexorcist._ui import STYLES, err, out

PACKAGE = Path(pdfexorcist.__file__).parent  # installed, as in Pyodide, or the checkout
README = Path(__file__).parent.parent / "README.md"
NAMES = "|".join(sorted(map(re.escape, [*STYLES, "bold", "dim"]), key=len, reverse=True))
MARKUP = re.compile(rf"\[((?:bold |dim )?(?:{NAMES})(?: [a-z.]+)?)\]")
STYLE_ARG = re.compile(r'(?:border_|header_)?style="([^"]+)"')


def test_every_style_resolves():
    """Pin theme names: Rich parses "bold accent" as a raw style and fails on "accent"."""
    used = set()
    for f in PACKAGE.glob("*.py"):
        if f.name != "show_assets.py":  # CSS for the HTML view
            text = f.read_text()
            used |= set(MARKUP.findall(text)) | set(STYLE_ARG.findall(text))
    assert used
    for style in used:
        out.get_style(style)  # raises MissingStyle


@pytest.fixture
def strict_styles(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail on an unknown style; Rich otherwise prints its text plain."""
    for console in (out, err):
        get = console.get_style
        monkeypatch.setattr(console, "get_style", lambda name, default=None, get=get: get(name))


@pytest.mark.usefixtures("strict_styles")
@pytest.mark.parametrize("args", [[], ["engines"], ["recipe", "show", "cpcb_aqi"]])
def test_screens_render(args):
    r = run(args)
    assert r.exit_code == 0, r.output


@pytest.mark.skipif(not README.exists(), reason="no README.md (Pyodide)")
def test_readme_lists_the_start_screen():
    """Pin README.md's common commands to the start screen's, word for word."""
    readme = README.read_text()
    for cmd, what in COMMON:
        assert re.search(rf"^{re.escape(cmd)} +# {re.escape(what)}$", readme, re.M), cmd
