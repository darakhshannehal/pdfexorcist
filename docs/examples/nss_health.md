---
description: "The NSS 75th round health Key Indicators read with a recipe: Appendix A's detailed tables, each value tied to its table, block and row, the block named by its sector, gender or State, although engines disagree on where that side label sits."
---

# NSS health Key Indicators: detailed tables

The National Sample Survey (NSS) 75th round asked households about health care in 2017-18. MoSPI published the Key Indicators of Social Consumption in India: Health (KI 75/25.0) as a PDF. Its Appendix A holds 37 detailed tables: illness, spending per spell of ailment and per hospitalisation, childbirth, the aged and immunisation.

Most tables repeat their rows for Rural, Urban and Rural + Urban. The sector is printed once, beside the middle of its block. Table A26 also repeats them for Male, Female and All, and puts the sector in the page header. The tables by State/UT (A8, A13, ...) print the State beside the first row of its block.

The files are in `examples/nss_health/`: `recipe.toml` and `nss_ki75.py`. The fixture is pages A-28 to A-33 of the report (Tables A23 to A32), in `tests/fixtures/nss_health/`.

## The recipe

```toml
name = "NSS KI 75: health detailed tables"

[pages]
match = 'Table A\d+:'

[engines]
ocr = false
use = ["pdftotext", "pdfplumber", "pymupdf", "pdfium"]

[parser]
type = "custom"
function = "nss_ki75.py:parse"
key = ["table", "block", "row", "col"]

[[checks]]
function = "nss_ki75.py:shares_add_up"

[output]
layout = "table"
rows = ["table", "block", "sector", "group", "area", "label", "n"]
columns = "col"
format = "csv"
```

The four fast text engines read the text layer, and 3 must agree. In a block whose `all` row is 100.0 in every column, the check adds up the other rows.

## The side label

The engines put a side label in different places, and the place also depends on where the label falls in each table:

- on a line of its own (`Rural`);
- in the first cell of a row (`Rural | private hospital | 1158 | 1015 | 1081`);
- joined to the row label in one cell (pdftotext: `Urban Percentage of cases receiving surgery`).

If a row is keyed by its label, the engines key that row differently, and no cell gets a quorum. `nss_ki75.py` takes the side label out of the row in all three forms:

- A first cell is a side label when it is a sector or gender word, or when the same row label follows several different first cells (a State name). A first cell that ends in `:` (`Private hospital:`) is a heading.
- A joined word is taken off only when the rest is a row label of the table.
- A side label before the first row of a table is a column heading and is not used.

A block starts where the table's first row label comes back. The side labels read in the block give its `sector`, `group` (Male, Female, All) and `area` (State/UT). A block without one leaves them empty.

## Other layout points

- A label can wrap onto a second line (`Charitable/NGO run` / `hospitals` in Table A25). pymupdf and pdfium put the values on the first line. pdftotext and pdfplumber read the first line alone and the values on a line without a label. A line of values takes the label of the line just above it.
- `below 20` (Table A27) ends in a number. The number goes back to the label when the row has one value more than the other rows of the table, so `45 & above` keeps its values.
- In Table A30, `Private hospital: All` heads `Normal delivery` and `Caesarean delivery`. The heading is added to those labels.
- pdfium drops a space before a bracket (`1st(lowest 20% of population)`). Rows are keyed with `label_key`.

## Run it

```bash
pdfexorcist extract tests/fixtures/nss_health/nss_ki75_appendix_p68-73.pdf --recipe examples/nss_health/recipe.toml -o ki75.csv
```

```
Agreed      801  100.0% of cells
Unresolved    0
```

```
table,block,sector,group,area,label,n,page,0,1,2,3,4,5,6,7
A23,1,Rural,,,government/public hospital,1,1,373,285,325,,,,,
A23,1,Rural,,,charitable/trust/NGO-run hospital,1,1,627,621,624,,,,,
A23,1,Rural,,,private hospital,1,1,1158,1015,1081,,,,,
```

On the whole report the check passes. The unresolved cells are in Table A11 (a superscript `st` in `1st`) and Table A21, whose side labels mix characteristics and sectors.

## Use

`healthsurveyindia` (an R package for the NSS health microdata) checks the published values of its factsheet against the reports. It reads every report with these four engines, and each value must be on a page of its table.
