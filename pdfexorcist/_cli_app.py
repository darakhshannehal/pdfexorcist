"""Typer apps and the welcome screen."""

from importlib.metadata import PackageNotFoundError, version
from typing import Annotated

import typer
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from typer import rich_utils

from ._ui import STYLES, out

# --help shares the CLI's colour for anything to type
rich_utils.STYLE_OPTION = rich_utils.STYLE_SWITCH = STYLES["command"]
rich_utils.STYLE_COMMANDS_TABLE_FIRST_COLUMN = STYLES["command"]

COMMON = [  # the start screen's commands; README.md lists the same
    ("pdfexorcist inspect report.pdf", "show which pages have text and which are scans"),
    ("pdfexorcist extract report.pdf", "write the agreed values to report.csv"),
    ("pdfexorcist extract photo.jpg --ocr", "read a scan or a photo with OCR"),
    ("pdfexorcist show report.pdf --page 3", "show what the engines read on page 3"),
    ("pdfexorcist recipe suggest report.pdf", "find a shipped recipe for this PDF"),
    ("pdfexorcist recipe new report.pdf", "save the settings for one kind of table"),
    ("pdfexorcist charts report.pdf", "read the points of line charts"),
    ("pdfexorcist engines", "list the engines and how to install more"),
]
HELP = [
    ("pdfexorcist extract --help", "options and examples for one command"),
    ("pdfexorcist --help", "all commands"),
]

try:
    __version__ = version("pdfexorcist")
except PackageNotFoundError:  # running from a source checkout
    __version__ = "0+unknown"

app = typer.Typer(
    name="pdfexorcist",
    help="Extract tables from PDFs and images by majority vote.",
    rich_markup_mode="rich",
    add_completion=False,
    context_settings={"help_option_names": ["-h", "--help"]},
    pretty_exceptions_enable=False,
)
recipe_app = typer.Typer(
    help="Save the settings for one kind of table in a recipe file. Use them again later.",
    no_args_is_help=True,
    rich_markup_mode="rich",
    context_settings={"help_option_names": ["-h", "--help"]},
)
app.add_typer(recipe_app, name="recipe")

COMMANDS = {"extract", "inspect", "engines", "doctor", "recipe", "show", "compare", "charts"}
OUT_PANEL, ENG_PANEL, ADV_PANEL = "Output", "Engines and pages", "Advanced"

Force = Annotated[
    bool,
    typer.Option("--force", rich_help_panel=OUT_PANEL, help="Replace existing output files."),
]
Quiet = Annotated[
    bool, typer.Option("--quiet", "-q", rich_help_panel=ADV_PANEL, help="Print only errors.")
]
Debug = Annotated[
    bool,
    typer.Option("--debug", rich_help_panel=ADV_PANEL, help="Show full error details and logs."),
]
Ocr = Annotated[
    bool,
    typer.Option(
        "--ocr",
        rich_help_panel=ENG_PANEL,
        help="Also read the page image with the installed OCR engines. Use it for scans and "
        "photos.",
    ),
]
ShowOcr = Annotated[
    bool,
    typer.Option(
        "--ocr",
        rich_help_panel=ENG_PANEL,
        help="Also read the page image with the installed OCR engines (scans, photos).",
    ),
]
Engines = Annotated[
    str | None,
    typer.Option(
        "--engines",
        "-e",
        rich_help_panel=ENG_PANEL,
        show_default=False,
        metavar="NAMES",
        help="Engines to use, comma-separated, e.g. pdfplumber,pymupdf,pdfium. See: pdfexorcist "
        "engines.",
    ),
]
ShowEngines = Annotated[
    str | None,
    typer.Option(
        "--engines",
        "-e",
        rich_help_panel=ENG_PANEL,
        show_default=False,
        metavar="NAMES",
        help="Engines to use, comma-separated. See: pdfexorcist engines.",
    ),
]
MinAgree = Annotated[
    int | None,
    typer.Option(
        "--min-agree",
        "-k",
        rich_help_panel=ENG_PANEL,
        show_default=False,
        metavar="N",
        help="Number of engines that must read the same value. Default: more than half, at "
        "least 3 (2 when only OCR engines read).",
    ),
]
Jobs = Annotated[
    int,
    typer.Option(
        "--jobs",
        "-j",
        min=1,
        rich_help_panel=ENG_PANEL,
        metavar="N",
        help="Run up to N engines at the same time, each in its own process.",
    ),
]
ShowMinAgree = Annotated[
    int | None,
    typer.Option(
        "--min-agree",
        "-k",
        rich_help_panel=ENG_PANEL,
        show_default=False,
        metavar="N",
        help="Number of engines that must read the same value. Default: more than half.",
    ),
]


def _version(value: bool) -> None:
    if value:
        out.print(f"pdfexorcist {__version__}")
        raise typer.Exit()


def welcome() -> None:
    """The screen shown by a bare pdfexorcist."""
    body = Text.assemble(
        ("Extracts tables from PDFs and images. ", "bold"),
        "Several engines read each page. A value is kept when most engines read the same "
        "value. A cell without a majority stays blank and goes to the review file.",
    )
    out.print(
        Panel(
            body,
            title=f"[bold]pdfexorcist {__version__}[/]",
            title_align="left",
            border_style="accent",
        )
    )
    out.print("[bold]Get started[/]")
    out.print(_commands(COMMON))
    out.print("\n[bold]Help[/]")
    out.print(_commands(HELP))


def _commands(rows: list[tuple[str, str]]) -> Table:
    """Commands to type beside what each does."""
    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="command", no_wrap=True)
    grid.add_column(style="dim")
    for cmd, what in rows:
        grid.add_row("  " + cmd, what)
    return grid


@app.callback(invoke_without_command=True)
def root(
    ctx: typer.Context,
    show_version: bool = typer.Option(
        False,
        "--version",
        "-V",
        callback=_version,
        is_eager=True,
        help="Show the version and exit.",
    ),
) -> None:
    """Extract tables from PDFs and images by majority vote."""
    if ctx.invoked_subcommand is None:
        welcome()
