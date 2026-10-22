---
description: "Every pdfexorcist command: extract, inspect, engines, show, compare, charts and recipe, with options, examples and exit codes."
---

# Command line

The `pdfexorcist` command reads a PDF or image and writes the values its engines agree on. Run it with no arguments for a short list of common commands.

Append `--help` to any command for its options and examples:

```bash
pdfexorcist --help
pdfexorcist extract --help
```

`python -m pdfexorcist` works the same way.

Every command that takes a file also takes a link (`https://...`). pdfexorcist saves the file in the current folder. A link that names its file is reused on the next run; any other is saved with the time it was downloaded in its name, so a link that serves the latest report gives a new file each time. pdfexorcist follows Drive, Dropbox and GitHub share links and download pages to the file. A tweet link reads the tweet's photo (`.../photo/2` the second). When a server leaves an intermediate certificate out of its chain, pdfexorcist verifies it with the certificate its own certificate names.


## extract

`extract` reads every page and writes the agreed values next to the input.

```bash
pdfexorcist extract report.pdf
```

```
Reading report.pdf with 5 engines (a majority must agree)
✓ pdftotext   242 readings  0.0s
✓ pdfplumber  242 readings  0.1s
✓ pymupdf     242 readings  0.0s
✓ camelot     237 readings  0.3s
✓ pdfium      243 readings  0.0s

✓  Agreed      242  99.6% of cells
!  Unresolved    1  engines disagreed, left blank

   Wrote   report.csv  48 rows, table layout
   Review  report.review.csv  cells to check, with each engine's reading
```

It writes two files:

* `report.csv`: the agreed values as a grid, one row per table row. A cell the engines disagreed on is blank.
* `report.review.csv`: one row per blank or failing cell, with the reason, the votes and what each engine read.

```
reason,page,row,col,label,value,status,failed,n_agree,votes,sources,dissent
engines disagreed,1,#3,0,,,unresolved,,1,9×1,pdfium,camelot=<missing>|pdfplumber=<missing>|pdftotext=<missing>|pymupdf=<missing>
```

`pdfexorcist report.pdf` is short for `pdfexorcist extract report.pdf`. An existing output file stops the run with an error unless you add `--force`.

### Extract options

| Option | Description |
| --- | --- |
| `-p`, `--pages` | Pages to read: `"3"`, `"1-3,7"`, `"10-"`. Default: all, or the recipe's. |
| `--pages-matching` | Read the pages whose text matches this regular expression (case-insensitive). A page without usable text, such as a font without a Unicode map, is matched on OCR of its top strip when tesseract is installed. `--pages` wins over it. |
| `--ocr` | Also read the page image with the installed OCR engines. Use it for scans and photos. An image turns it on by itself. |
| `-e`, `--engines` | Engines to use, comma-separated, e.g. `pdfplumber,pymupdf,pdfium`. |
| `-k`, `--min-agree` | Number of engines that must read the same value. Default: more than half, at least 3 (2 when only OCR engines read). |
| `-j`, `--jobs` | Use up to N worker processes: engines run at once, and each splits its pages into up to N chunks, so one engine on a long PDF gets faster too. Chandra and GLM-OCR read in this process. The result is the same. Default: 1. |
| `-r`, `--recipe` | Settings saved in a [recipe](recipes.md): a file, or the name of a shipped recipe (`cpcb_aqi`). Command-line options override it. |
| `-o`, `--output` | A file or a folder (a name without an ending). The file ending sets the format. Default: next to the input. |
| `-f`, `--format` | `csv` (default), `xlsx`, `parquet` or `json`. |
| `--layout` | `table` (default): the grid plus the review file. `cells`: one row per cell with every engine's reading. |
| `--force` | Replace existing output files. |
| `-q`, `--quiet` | Print only errors. |
| `--json` | Print a machine-readable summary on stdout. |
| `--debug` | Show full error details and logs. |

```bash
pdfexorcist extract report.pdf --pages 3-5 -o tables.xlsx
pdfexorcist extract report.pdf -o out/                       # out/report.csv, out/report.review.csv
pdfexorcist extract report.pdf --recipe states.toml
```

`--layout cells` keeps the evidence for every cell:

```bash
pdfexorcist extract report.pdf --layout cells -o cells.csv
```

```
page,row,col,label,value,status,failed,n_agree,votes,sources,dissent
1,populationcrimesipc#1,0,Population Crimes (IPC),(2021),verified,,4,(2021)×4,pdfium|pdfplumber|pdftotext|pymupdf,camelot=<missing>
1,inlakhs#1,0,(in Lakhs),(2021),verified,,5,(2021)×5,camelot|pdfium|pdfplumber|pdftotext|pymupdf,
```

### Scans and photos

```bash
pdfexorcist extract scan.pdf --ocr
pdfexorcist extract photo.jpg --recipe pdfexorcist/recipes/mybmc_lakes/recipe.toml
```

On a photo the generic parser rarely lines up the OCR engines' rows. A recipe with a parser for that layout does; see [Recipes](recipes.md#example-mybmc-lakes-a-photographed-table).


## inspect

`inspect` tells you whether a file has a text layer, and which command to run.

```bash
pdfexorcist inspect report.pdf
```

```
report.pdf: 1 page
Pages   Content   Characters   Size
───────────────────────────────────────────
1       text           2,196   A4 portrait

It has a text layer, which the default engines read fast and exactly.

  Run  pdfexorcist extract report.pdf
```

```bash
pdfexorcist inspect photo.jpg
```

```
photo.jpg: an image, 949 x 1146 pixels.
Only OCR engines can read it.

  Run  pdfexorcist extract photo.jpg --ocr
```

`--json` prints the per-page details, including whether the text layer came from ocrmypdf.


## engines

`engines` lists every engine, whether it is installed, and the command that installs a missing one. `doctor` is the same command.

```bash
pdfexorcist engines
pdfexorcist engines --json
```

See [Installation](installation.md#check-what-is-installed) for its output and [Engines](engines.md) for what each engine reads.


## show

`show` draws one page with a box on every cell the vote produced. It writes one HTML file that works offline.

```bash
pdfexorcist show report.pdf --page 3                 # writes report.p3.show.html
pdfexorcist show report.pdf -p 3 --recipe mccd.toml --open
pdfexorcist show photo.jpg --ocr --png               # also a static PNG
pdfexorcist show report.pdf -p 3 -o page3.png        # only the PNG
```

| Option | Description |
| --- | --- |
| `-p`, `--page` | The page to show. Default: the recipe's first page, or page 1. |
| `-r`, `--recipe` | Use a recipe's parser, checks and engines: a file, or the name of a shipped recipe. |
| `-o`, `--output` | `.html`, `.png`, or a folder. Default: `<name>.p<page>.show.html`. |
| `--png` | Also write a static annotated PNG. |
| `--open` | Open the result in the default browser. |
| `--ocr`, `-e`, `-k` | As for `extract`. |
| `--force`, `-q`, `--debug` | As for `extract`. |

See [See what it extracts](show.md) for what the page shows.


## compare

`compare` writes the same file as `show`, opened on its engines-side-by-side view.

```bash
pdfexorcist compare report.pdf --page 3              # writes report.p3.compare.html
pdfexorcist compare scan.pdf -p 2 --ocr --open
```

It takes the same options as `show`.


## charts

`charts` reads the points of line charts, for example Excel charts in a Word document. It writes one row for each point: `page`, `chart`, `title`, `series`, `category`, `value` and `status`.

```bash
pdfexorcist charts report.pdf                        # writes report.charts.csv
pdfexorcist charts report.pdf -p 3,4 -o out.json
pdfexorcist charts report.pdf --recipe ncvbdc_charts   # charts in pictures
```

| Option | Description |
| --- | --- |
| `-p`, `--pages` | Pages to read, for example `"3"` or `"1-3,7"` or `"10-"`. Default: the recipe's pages, or all. |
| `-r`, `--recipe` | A recipe with a `[charts]` section, or the name of a shipped recipe. See [Charts](recipes.md#charts). |
| `-o`, `--output` | `.csv`, `.json` or `.parquet`. Default: `<name>.charts.csv`. |
| `--json` | Print a summary as JSON: `outputs`, `points`, `charts`, `status`, `failed_checks`, `skipped`, `notes`. |
| `--force`, `--debug` | As for `extract`. |

A chart that is vector paths gives each value from a position. Thus, the value is approximate. `pm` gives the maximum error, and `status` is `estimated`.

A chart that is a picture needs OCR engines. The engines read the value printed in each box and vote. `status` is `verified` or `unresolved`, and `votes` shows what each engine read. `line_value` is the value of the series line at that category. If the two values do not agree, the `failed` column shows "value off its line".

If pdfexorcist cannot read a chart, it does not read that chart. The output gives the chart and the cause. If the command finds no chart, or a value fails a check, the exit code is 1. Refer to [NCVBDC line charts](examples/ncvbdc_charts.md) for examples.


## recipe

A recipe saves the settings for one kind of table in a TOML file. See [Recipes](recipes.md) for the format.

### recipe new

`recipe new` asks a few questions, tries the answers on your file, shows the first rows, and saves the recipe. Each option answers one question; `--yes` asks nothing.

```bash
pdfexorcist recipe new report.pdf
pdfexorcist recipe new report.pdf --yes --min-values 3 --clean commas,footnotes \
    --total "label: TOTAL ALL INDIA = TOTAL STATE(S) + TOTAL UT(S)" -o states.toml
```

```
Trying the recipe on page 1 of report.pdf ...
234 values agreed, 0 cells unresolved.
First rows of the result (blank = engines disagreed)
 page ┃ label               ┃ 0      ┃ 1      ┃ 2      ┃ 3      ┃ 4     ┃ 5
━━━━━━╇━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━╇━━━━━━━━╇━━━━━━━━╇━━━━━━━╇━━━━━━
 1    │ 1 Andhra Pradesh    │ 119229 │ 188997 │ 179611 │ 528.5  │ 339.9 │ 92.9
 1    │ 2 Arunachal Pradesh │ 2590   │ 2244   │ 2626   │ 15.4   │ 170.9 │ 51.7
...
9 values break a rule on the sample pages (marked in the failed column when you run it).

Saved states.toml.
```

| Option | Description |
| --- | --- |
| `-p`, `--pages` | Pages with the table. |
| `--page-text` | Use only pages whose text matches this regular expression. |
| `--ocr` / `--no-ocr` | Read with OCR engines. Default: on for scans and images. |
| `--parser` | `rows` (values in reading order) or `columns` (values placed by position). |
| `--min-values` | Skip lines with fewer values. Default: 2. |
| `--clean` | `commas`, `footnotes`, `raised-dots`, `minus`. Default: those seen on the sample. |
| `--total` | A total that must add up, `"COLUMN: RULE"`. Repeatable. |
| `-e`, `--engines`, `-k`, `--min-agree`, `-j`, `--jobs` | As for `extract`. |
| `--name` | A short name for the recipe. |
| `-o`, `--output` | Recipe file to write. Default: `<sample>.recipe.toml`. |
| `-y`, `--yes` | Ask nothing. |
| `--no-preview` | Do not try the recipe on the sample. |
| `--force` | Replace an existing recipe file. |

### recipe check

`recipe check` reports any mistake with its line number, and imports any Python the recipe names.

```bash
pdfexorcist recipe check states.toml
```

```
OK: states.toml is a valid recipe.
Use it with: pdfexorcist extract YOUR.pdf --recipe states.toml
```

### recipe suggest

`recipe suggest` finds the shipped recipe for a PDF. It takes three steps:

1. It compares the PDF's words with each recipe's sample. A recipe whose page text is in the PDF gets a bonus.
2. It compares the layout: the shapes of the lines (text, whole numbers, decimals, dates) and the column positions.
3. It runs the best recipes from each step with one engine. A recipe fits when its checks pass and it reads at least a fifth of the numbers on its pages.

```bash
pdfexorcist recipe suggest bulletin.pdf
```

```
Shipped recipes for bulletin.pdf

Recipe                      ┃ Words      ┃ Layout     ┃ Pages ┃ Trial run (one engine)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
cpcb_aqi                    │ █████ 100% │ █████  99% │   ✓   │ fits: 318 cells, 100% of the
CPCB AQI bulletin           │            │            │       │ numbers
srs_maternal_mortality/age  │ █░░░░  17% │ █░░░░  24% │   ✗   │ reads nothing
SRS maternal deaths by age  │            │            │       │
karnataka_idsp              │ ░░░░░   9% │ █░░░░  30% │   –   │ reads nothing
Karnataka IDSP weekly report│            │            │       │

Fits: CPCB AQI bulletin. Use it with:
  pdfexorcist extract bulletin.pdf --recipe cpcb_aqi
```

When no recipe fits, it names the recipe with the closest layout and suggests `recipe new`. The closest recipe's parser may look for headings this PDF does not print.

A photo, a link to one, or a scanned PDF has no text layer. Tesseract reads its words and layout, and the trial runs with an installed OCR engine that the recipe names. When none of them is installed, the trial does not run and `suggest` names the engines to install:

```bash
pdfexorcist recipe suggest https://x.com/mybmc/status/2108041806676148568
```

```
mybmc_lakes  │ ████░  75% │ ████░  78% │   –   │ fits: 119 cells, 100% of the numbers
MyBMC lakes  │            │            │       │
...
No text layer: tesseract reads the words and layout, and each trial runs with an OCR engine its recipe names.
```

| Option | Description |
| --- | --- |
| `-j`, `--jobs` | Try up to N recipes at once, each in its own process. Default: 1. |
| `--json` | Print the scores and trial runs as JSON. |

### recipe show

`recipe show` explains a recipe in plain words. It runs none of its code. `--raw` prints the file with colours; `--json` prints the settings.

```bash
pdfexorcist recipe show states.toml
```

```
╭─ states.toml ──────────────────────────────────────────────────────────────────────────╮
│ Name          report                                                                   │
│ Made with     report.pdf                                                               │
│ Pages         every page                                                               │
│ Engines       the installed default engines                                            │
│ Agreement     a strict majority, at least 3 (2 for OCR-only votes)                     │
│ Clean values  remove thousands commas; remove footnote marks (490* -> 490)             │
│ Parser        values in reading order (rows); rows with at least 3 values              │
│ Check         label 'TOTAL ALL INDIA' = TOTAL STATE(S) + TOTAL UT(S), within each      │
│               page, col                                                                │
│ Output        csv, table layout                                                        │
╰────────────────────────────────────────────────────────────────────────────────────────╯
```


## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | Done. Some cells may be unresolved; they are in the review file. |
| `1` | Nothing agreed, a check failed, or too few engines could run. |
| `2` | A usage problem: a missing file, a bad option, an invalid recipe, an output that exists. |

The recipe above checks that India's total equals States plus UTs in every column. Population (column 3) is rounded and rates (4, 5) do not add up, so it fails there:

```bash
pdfexorcist extract report.pdf --recipe states.toml
```

```
✓  Agreed         234  100.0% of cells
   Unresolved       0
✗  Failed checks    9  agreed values break a rule
    ✗ label 'TOTAL ALL INDIA' = TOTAL STATE(S) + TOTAL UT(S), within each page, col: 9 cells

   Wrote   report.csv  39 rows, table layout
   Review  report.review.csv  cells to check, with each engine's reading

Some agreed values break a rule (see the failed column). The exit code is 1.
```

Adding `where = "col <= 2"` to the check limits it to the count columns; see [Recipes](recipes.md#checks).

An error prints what went wrong and how to fix it:

```
╭─ Error ────────────────────────────────────────────────────────────────────────────────╮
│ Only 2 engines can run here (pdfplumber, pymupdf), but a value needs 3 agreeing        │
│ readings.                                                                              │
│                                                                                        │
│ How to fix: Install more engines (pdfexorcist engines shows how), or choose them with  │
│ --engines.                                                                             │
╰────────────────────────────────────────────────────────────────────────────────────────╯
```


## Scripts

`--json --quiet` prints only a JSON summary, with the same [exit codes](#exit-codes):

```bash
pdfexorcist extract report.pdf --json --quiet
```

```json
{
  "pdfexorcist": "0.1.0",
  "input": "report.pdf",
  "outputs": ["report.csv", "report.review.csv"],
  "review": "report.review.csv",
  "format": "csv",
  "layout": "table",
  "pages": null,
  "engines": {
    "used": {"pdftotext": 242, "pdfplumber": 242, "pymupdf": 242, "camelot": 237, "pdfium": 243},
    "skipped": {}
  },
  "min_agree": null,
  "cells": {"total": 243, "verified": 242, "unresolved": 1, "failed_checks": 0},
  "agreement": {"5": 236, "4": 6},
  "table": {"rows": 48, "columns": 8},
  "checks": {},
  "checks_run": [],
  "notes": [],
  "exit_code": 0
}
```

```bash
for f in reports/*.pdf; do
  pdfexorcist extract "$f" --recipe states.toml -o out/ -q || echo "check $f"
done
```
