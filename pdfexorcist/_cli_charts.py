"""The charts command."""

from pathlib import Path
from typing import Any

import typer

from ._cli_app import OUT_PANEL, Debug, Force, app
from ._ui import EXIT_FAILED, guard, setup_logging

FORMATS = ("csv", "json", "parquet")


@app.command(
    epilog="[bold]Examples[/]\n\n"
    "  pdfexorcist charts report.pdf                 [dim]# writes report.charts.csv[/]\n\n"
    "  pdfexorcist charts report.pdf -p 3,4 -o out.json\n\n"
    "  pdfexorcist charts report.pdf --recipe ncvbdc_charts   [dim]# charts pasted as pictures[/]"
)
def charts(
    file: str = typer.Argument(
        ..., metavar="FILE", help="The PDF to read, or a link to one.", show_default=False
    ),
    pages: str | None = typer.Option(
        None,
        "--pages",
        "-p",
        metavar="PAGES",
        show_default=False,
        help='Pages to read, e.g. "3" or "1-3,7" or "10-". Default: the recipe\'s, or all.',
    ),
    recipe: Path | None = typer.Option(
        None,
        "--recipe",
        "-r",
        metavar="RECIPE",
        show_default=False,
        help="A recipe with a [charts] section, or a shipped recipe's name.",
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        metavar="PATH",
        rich_help_panel=OUT_PANEL,
        show_default=False,
        help="File to write (.csv, .json or .parquet). Default: <name>.charts.csv next to the "
        "input.",
    ),
    as_json: bool = typer.Option(
        False, "--json", help="Print a summary as JSON: outputs, points, charts, skipped charts."
    ),
    force: Force = False,
    debug: Debug = False,
) -> None:
    """Read the points of line charts. Drawn charts give each value a [cyan]pm[/] (plus or minus)
    and the status estimated; OCR engines read and vote on the values printed in a chart picture."""
    from ._output import _write_one
    from ._run import _page_count, load_recipe, need_format
    from ._ui import EXIT_FAILED, CliError, refuse_overwrite, resolve_input
    from .recipe import page_list

    with guard(debug, as_json):
        setup_logging(debug)
        src = resolve_input(file)
        rec = load_recipe(recipe)
        dest = output or src.with_suffix(".charts.csv")
        fmt = dest.suffix.lower().lstrip(".")
        if fmt not in FORMATS:
            raise CliError(
                f"Cannot write {dest.name}.", "Use a .csv, .json or .parquet name with -o."
            )
        need_format(fmt)
        refuse_overwrite([dest], force)
        try:
            numbers = page_list(rec, src, _page_count(src, False), pages)
        except ValueError as e:
            raise CliError(f"--pages: {e}") from e
        df = _read(src, numbers, rec)
        if df.empty:
            why = "; ".join(df.attrs["notes"]) or "set the pages, or use a recipe (--recipe)"
            raise CliError(f"Found no line chart in {src.name}.", why, code=EXIT_FAILED)
        _write_one(df, dest, fmt)
        _report(src, dest, df, as_json)


def _read(src: Path, pages: list[int] | None, rec: Any) -> Any:
    """read_charts with the recipe's settings, and its checks on the values that stand."""
    from .charts import read_charts
    from .checks import lossy, validate

    df = read_charts(src, pages, settings=rec.charts)
    if df.empty:
        df.attrs["checks_run"] = []
        return df
    checks = rec.check_functions()
    ok = df.status.isin(["verified", "estimated"])
    found = validate(df[ok], [*checks, lossy])["failed"].reindex(df.index, fill_value="")
    df.attrs["checks_run"] = [c.__name__ for c in checks]
    if "failed" not in df and not (found != "").any():
        return df  # a drawn chart that fails no check keeps its columns
    line = df["failed"].fillna("") if "failed" in df else ""  # the line check of picture charts
    return df.assign(failed=(line + "; " + found).str.strip("; "))


def _report(src: Path, dest: Path, df: Any, as_json: bool) -> None:
    """The summary on stdout (--json) or stderr; exit code 1 when a value fails a check or no
    value stands."""
    from ._ui import err, esc, path_text, plural, print_json

    skipped = [{"page": no, "chart": n, "reason": why} for no, n, why in df.attrs["skipped"]]
    failed = int((df.failed.fillna("") != "").sum()) if "failed" in df else 0
    status = df.status.value_counts().to_dict()
    n = df.groupby(["page", "chart"]).ngroups
    stands = int(df.status.isin(["verified", "estimated"]).sum())
    code = EXIT_FAILED if failed or not stands else 0
    if as_json:
        print_json(
            {
                "input": str(src),
                "outputs": [str(dest)],
                "points": len(df),
                "charts": n,
                "status": status,
                "failed_checks": failed,
                "checks_run": df.attrs["checks_run"],
                "skipped": skipped,
                "notes": df.attrs["notes"],
                "exit_code": code,
            }
        )
    else:
        for k in skipped:
            err.print(f"[warn]Skipped page {k['page']}, chart {k['chart']}:[/] {esc(k['reason'])}")
        for note in df.attrs["notes"]:
            err.print(f"[warn]Note:[/] {esc(note)}")
        votes = ", ".join(f"{v} {k}" for k, v in status.items())
        err.print(
            f"Wrote {plural(len(df), 'point')} from {plural(n, 'chart')} ({votes}) "
            f"to {path_text(dest)}."
        )
        if failed:
            err.print(f"[error]{plural(failed, 'value')} failed a check:[/] see the failed column.")
        if not stands:
            err.print("[error]No value was verified:[/] the engines did not agree on any.")
    if code:
        raise typer.Exit(code)
