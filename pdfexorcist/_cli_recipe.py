"""The recipe commands."""

from pathlib import Path
from typing import TYPE_CHECKING

import typer
from rich.panel import Panel
from rich.table import Table

from . import recipe as recipes
from ._cli_app import recipe_app
from ._recipe_text import as_dict, describe
from ._shipped import resolve_recipe
from ._ui import (
    CliError,
    cmd_arg,
    esc,
    guard,
    out,
    path_text,
    plural,
    print_json,
    resolve_input,
    setup_logging,
)

if TYPE_CHECKING:
    from ._suggest import Candidate


@recipe_app.command(
    "new",
    epilog="[bold]Examples[/]\n\n"
    "  pdfexorcist recipe new report.pdf                [dim]# asks a few questions[/]\n\n"
    "  pdfexorcist recipe new report.pdf --yes --pages 3-5 --parser rows "
    '--total "label: All India = rest" -o states.toml',
)
def recipe_new(
    sample: str | None = typer.Argument(
        None,
        metavar="SAMPLE",
        help="A PDF or image with the table, to try the recipe on.",
        show_default=False,
    ),
    pages: str | None = typer.Option(
        None,
        "--pages",
        "-p",
        metavar="PAGES",
        rich_help_panel="Answers (each skips its question)",
        help='Pages with the table, e.g. "3-5". Default: all.',
        show_default=False,
    ),
    page_text: str | None = typer.Option(
        None,
        "--page-text",
        metavar="REGEX",
        rich_help_panel="Answers (each skips its question)",
        help="Use only pages whose text matches this (a regular expression).",
        show_default=False,
    ),
    ocr: bool | None = typer.Option(
        None,
        "--ocr/--no-ocr",
        rich_help_panel="Answers (each skips its question)",
        help="Read with OCR engines (scans, photos). Default: on for scans and images.",
        show_default=False,
    ),
    parser: str | None = typer.Option(
        None,
        "--parser",
        metavar="rows|columns",
        rich_help_panel="Answers (each skips its question)",
        help="rows: values in reading order. columns: values placed by position (scans, blank "
        "cells).",
        show_default=False,
    ),
    min_values: int | None = typer.Option(
        None,
        "--min-values",
        metavar="N",
        rich_help_panel="Answers (each skips its question)",
        help="Skip lines with fewer values (titles, notes). Default: 2.",
        show_default=False,
    ),
    clean: str | None = typer.Option(
        None,
        "--clean",
        metavar="LIST",
        rich_help_panel="Answers (each skips its question)",
        help="Number clean-ups, comma-separated: commas, footnotes, raised-dots, minus. "
        "Default: the ones found on the sample page.",
        show_default=False,
    ),
    total: list[str] | None = typer.Option(
        None,
        "--total",
        metavar='"COLUMN: RULE"',
        rich_help_panel="Answers (each skips its question)",
        help="A total that must add up. Give it more than once for more totals. "
        '"label: All India = rest" is a total row. "col: 0 = 1 + 2" is a total column. '
        'Add "per page,row" to set where it applies.',
        show_default=False,
    ),
    engines: str | None = typer.Option(
        None,
        "--engines",
        "-e",
        metavar="NAMES",
        rich_help_panel="Answers (each skips its question)",
        help="Engines to use, comma-separated. Default: the installed ones.",
        show_default=False,
    ),
    min_agree: int | None = typer.Option(
        None,
        "--min-agree",
        "-k",
        metavar="N",
        rich_help_panel="Answers (each skips its question)",
        help="Engines that must agree. Default: a strict majority.",
        show_default=False,
    ),
    name: str | None = typer.Option(
        None,
        "--name",
        metavar="TEXT",
        rich_help_panel="Answers (each skips its question)",
        help="A short name for the recipe. Default: the sample's name.",
        show_default=False,
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        metavar="FILE",
        rich_help_panel="How to run",
        help="Recipe file to write. Default: <sample>.recipe.toml here.",
        show_default=False,
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        rich_help_panel="How to run",
        help="Ask nothing: use the options given and defaults for the rest.",
    ),
    preview: bool = typer.Option(
        True,
        "--preview/--no-preview",
        rich_help_panel="How to run",
        help="Try the recipe on the sample and show the first rows.",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        rich_help_panel="How to run",
        help="Replace an existing recipe file.",
    ),
    debug: bool = typer.Option(
        False, "--debug", rich_help_panel="How to run", help="Show full error details."
    ),
) -> None:
    """Create a recipe. Answer a few questions, or give options with --yes."""
    from ._wizard import WizardOptions, new_recipe

    with guard(debug):
        setup_logging(debug)
        for flag, n in (("--min-values", min_values), ("--min-agree", min_agree)):
            if n is not None and n < 1:
                raise CliError(f"{flag} must be 1 or more.")
        new_recipe(
            WizardOptions(
                sample=sample,
                output=output,
                name=name,
                pages=pages,
                page_text=page_text,
                parser=parser,
                min_values=min_values,
                clean=clean,
                totals=list(total or []),
                ocr=ocr,
                engines=engines,
                min_agree=min_agree,
                yes=yes,
                preview=preview,
                force=force,
            )
        )


@recipe_app.command("check", epilog="[bold]Example[/]\n\n  pdfexorcist recipe check states.toml")
def recipe_check(
    file: Path = typer.Argument(..., metavar="RECIPE", help="The recipe file.", show_default=False),
    as_json: bool = typer.Option(False, "--json", help="Print the result as JSON."),
    debug: bool = typer.Option(False, "--debug", help="Show full error details."),
) -> None:
    """Check a recipe for mistakes and name the line to fix. Also imports its Python files."""
    with guard(debug, as_json):
        setup_logging(debug)
        rec = recipes.load(resolve_recipe(file))
        rec.resolve_all()
        if as_json:
            print_json({"ok": True, "recipe": as_dict(rec)})
            return
        out.print(f"[ok]OK[/]: [bold]{esc(path_text(file))}[/] is a valid recipe.")
        out.print(
            f"Use it with: [command]pdfexorcist extract YOUR.pdf --recipe {esc(cmd_arg(file))}[/]"
        )


@recipe_app.command("show", epilog="[bold]Example[/]\n\n  pdfexorcist recipe show states.toml")
def recipe_show(
    file: Path = typer.Argument(..., metavar="RECIPE", help="The recipe file.", show_default=False),
    raw: bool = typer.Option(False, "--raw", help="Print the file itself, with colours."),
    as_json: bool = typer.Option(False, "--json", help="Print the settings as JSON."),
    debug: bool = typer.Option(False, "--debug", help="Show full error details."),
) -> None:
    """Explain what a recipe does. Runs none of its code."""
    with guard(debug, as_json):
        rec = recipes.load(resolve_recipe(file))
        if as_json:
            print_json(as_dict(rec))
            return
        if raw:
            from rich.syntax import Syntax

            out.print(
                Syntax(
                    (rec.path or Path(file)).read_text(encoding="utf-8"),
                    "toml",
                    line_numbers=True,
                    word_wrap=True,
                )
            )
            return
        t = Table.grid(padding=(0, 2))
        t.add_column(style="bold", no_wrap=True)
        t.add_column()
        for what, setting in describe(rec):
            t.add_row(what, esc(setting))
        out.print(
            Panel(
                t,
                title=f"[bold]{esc(path_text(file))}[/]",
                title_align="left",
                border_style="accent",
            )
        )
        out.print(f"Run it: [command]pdfexorcist extract YOUR.pdf --recipe {esc(cmd_arg(file))}[/]")


def _bar(score: float) -> str:
    """A score as a short bar and a percentage."""
    full = round(score * 5)
    return f"[accent]{'█' * full}[/][dim]{'░' * (5 - full)}[/] {score:>4.0%}"


def _verdict(c: "Candidate") -> str:
    """What the trial run of one recipe found."""
    if c.error:
        return f"[error]error[/] [dim]{esc(c.error)}[/]"
    if c.needs:
        return f"[warn]not run:[/] [dim]needs an OCR engine: {esc(', '.join(c.needs))}[/]"
    if not c.cells:
        return "[dim]reads nothing[/]"
    read = f"{plural(c.cells, 'cell')}, {min(c.coverage, 1):.0%} of the numbers"
    if c.failed:
        return f"[warn]{read}; fails {esc(c.failed[0])}[/]"
    return f"[ok]fits[/]: {read}" if c.fits else f"[warn]{read}[/]"


@recipe_app.command(
    "suggest",
    epilog="[bold]Examples[/]\n\n"
    "  pdfexorcist recipe suggest bulletin.pdf\n\n"
    "  pdfexorcist extract bulletin.pdf --recipe cpcb_aqi   [dim]# then use the one that fits[/]",
)
def recipe_suggest(
    file: str = typer.Argument(
        ..., metavar="FILE", help="The PDF, or a link to one.", show_default=False
    ),
    jobs: int = typer.Option(
        1,
        "--jobs",
        "-j",
        min=1,
        metavar="N",
        help="Try up to N recipes at the same time, each in its own process.",
    ),
    as_json: bool = typer.Option(False, "--json", help="Print the result as JSON."),
    debug: bool = typer.Option(False, "--debug", help="Show full error details."),
) -> None:
    """Find a shipped recipe for a PDF. Matches by words, then layout, then a trial run."""
    from ._suggest import suggest

    with guard(debug, as_json):
        setup_logging(debug)
        pdf = resolve_input(file)
        found, scan = suggest(pdf, jobs)
        if as_json:
            print_json(
                {
                    "file": str(pdf),
                    "scan": scan,
                    "recipes": [
                        {
                            "recipe": c.recipe,
                            "name": c.title,
                            "fits": c.fits,
                            "words": round(c.words, 3),
                            "layout": round(c.layout, 3),
                            "page_match": c.page_match,
                            "cells": c.cells,
                            "coverage": round(c.coverage, 3),
                            "failed_checks": c.failed,
                            "error": c.error or None,
                            "engine": c.engine,
                            "needs": c.needs,
                        }
                        for c in found
                    ],
                }
            )
            return
        t = Table(header_style="bold", show_edge=False, pad_edge=False)
        t.add_column("Recipe", no_wrap=True)
        t.add_column("Words", no_wrap=True)
        t.add_column("Layout", no_wrap=True)
        t.add_column("Pages", justify="center")
        t.add_column("Trial run (one engine)")
        for c in found:
            name = f"[command]{esc(c.recipe)}[/]\n[dim]{esc(c.title)}[/]"
            pages = {True: "[ok]✓[/]", False: "[dim]✗[/]", None: "[dim]–[/]"}[c.page_match]
            t.add_row(name, _bar(c.words), _bar(c.layout), pages, _verdict(c))
        out.print(f"\n[bold]Shipped recipes for[/] {esc(pdf.name)}\n")
        out.print(t)
        out.print(
            "\n[dim]Words: the share of the recipe sample's words in this PDF. Layout: how alike "
            "the line shapes and column positions are. Pages: whether the recipe's page text is "
            "in this PDF.[/]"
            + (
                "\n[dim]No text layer: tesseract reads the words and layout, and each trial runs "
                "with an OCR engine its recipe names.[/]"
                if scan
                else ""
            )
        )
        best = next((c for c in found if c.fits), None)
        if best:
            out.print(
                f"\n[ok]Fits:[/] [bold]{esc(best.title)}[/]. Use it with:\n"
                f"  [command]pdfexorcist extract {esc(cmd_arg(pdf))} "
                f"--recipe {esc(best.recipe)}[/]",
                soft_wrap=True,
            )
            return
        near = max(found, key=lambda c: c.layout, default=None)
        out.print("\n[warn]No shipped recipe fits this PDF.[/]")
        likely = found[0] if found and found[0].needs else None  # sorted by score
        if likely:
            out.print(
                f"Best match: [bold]{esc(likely.title)}[/] ([command]{esc(likely.recipe)}[/]). "
                f"Trying it needs one of its OCR engines: {esc(', '.join(likely.needs))}; "
                "[command]pdfexorcist engines[/] shows how to install them.",
                soft_wrap=True,
            )
        if near and near is not likely:
            out.print(
                f"Closest layout: [bold]{esc(near.recipe)}[/]. Read it with "
                f"[command]pdfexorcist recipe show {esc(near.recipe)} --raw[/]; its parser may "
                "expect other headings."
            )
        out.print(
            f"Make a recipe with: [command]pdfexorcist recipe new {esc(cmd_arg(pdf))}[/]",
            soft_wrap=True,
        )
