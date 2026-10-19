---
description: "The SRS Statistical Report 2024 read with a recipe: Table 1's percent distribution of the population by age, sex and residence for every bigger State, each value tied to its State, with checks that each column adds up to 100 and each total lies between its parts."
---

# SRS Statistical Report: age distribution

The Sample Registration System (SRS) publishes its yearly estimates of births, deaths and fertility only as a PDF. Table 1 of the [SRS Statistical Report 2024](https://censusindia.gov.in/nada/index.php/catalog/47152/download/51396), on pages 222-233, gives the percent distribution of the estimated population by age group, sex and residence.

Each page holds one or two blocks. A block is a State name (or `India`), 18 age rows from `0-4` to `85+`, and a `Total` row of `100.0`. Its nine columns sit under a two-level header: Total, Rural and Urban, each split into Total, Males and Females.

The files are in `pdfexorcist/recipes/srs_statistical_report/`: `recipe.toml` and `srs_stat.py`. The fixture is pages 222-224 of the report (India, Andhra Pradesh, Assam, Bihar, Chhattisgarh), in `tests/fixtures/srs_stat/`. The life tables from the same survey have [their own example](srs.md).

## The recipe

```toml
name = "SRS Statistical Report: age distribution"

[pages]
match = 'Percent distribution of estimated population by age'

[engines]
ocr = false

[parser]
type = "custom"
function = "srs_stat.py:parse"
key = ["page", "block", "age", "col"]

# each column's 18 age groups add up to its printed 100.0, within rounding
[[checks]]
column = "age"
rule = "Total = rest"
by = ["page", "block", "col"]
abs_tolerance = 0.5
name = "age groups add up to 100"

[[checks]]
function = "srs_stat.py:total_between_parts"

[output]
layout = "table"
rows = ["state", "age"]
columns = "col"
format = "csv"
```

`match` keeps the Table 1 pages.

A cell is keyed by its block on the page (counted by the `0-4` row, which every engine reads), its age group and its column (`total_total`, `total_males`, ..., `urban_females`). The State heading is an extra column, so an engine that misses it still votes.

## Run it

```bash
pdfexorcist extract srs_stat_2024.pdf --recipe pdfexorcist/recipes/srs_statistical_report/recipe.toml -o srs_table1.csv
```

On the whole report, every cell agrees and both checks pass. On the fixture:

```bash
pdfexorcist extract tests/fixtures/srs_stat/srs_stat_2024_table1_p222-224.pdf --recipe pdfexorcist/recipes/srs_statistical_report/recipe.toml -o srs_table1.csv
```

```
✓ pdftotext   855 readings  0.0s
✓ pdfplumber  855 readings  0.1s
✓ pymupdf     855 readings  0.0s
✓ camelot     855 readings  1.4s
✓ pdfium      855 readings  0.0s

✓  Agreed          855  100.0% of cells
   Unresolved        0
✓  Checks      2 rules  all passed

   Wrote   srs_table1.csv  95 rows, table layout
```

```
state,age,total_total,total_males,total_females,rural_total,rural_males,rural_females,urban_total,urban_males,urban_females
India,0-4,7.9,8.1,7.7,8.6,8.8,8.3,6.6,6.8,6.4
India,5-9,7.7,7.9,7.5,8.2,8.4,8.0,6.8,7.0,6.7
...
India,Total,100.0,100.0,100.0,100.0,100.0,100.0,100.0,100.0,100.0
Andhra Pradesh,0-4,6.4,6.6,6.1,6.5,6.8,6.1,6.2,6.2,6.3
...
Chhattisgarh,85+,0.2,0.2,0.2,0.2,0.2,0.2,0.3,0.3,0.3
Chhattisgarh,Total,100.0,100.0,100.0,100.0,100.0,100.0,100.0,100.0,100.0
```

## The parser

`parse()` in `srs_stat.py`, in outline (pseudocode):

```text
def parse(pages):
    for page_no, lines in pages:
        for line in lines:
            a line of words only, not a header      -> the next block's State
            "<age group or Total>" then 9 numbers
                -> "0-4" starts a new block
                -> yield {"page", "block", "age", "col": total_total ... urban_females,
                          "value", "state"}
```

The title ends in `2024`, which looks like a value; the parser keeps only rows labelled with an age group or `Total`.

## The checks

* Age groups add up to 100. In each block and column, the 18 age groups add up to the printed `Total`. Each group is rounded to one decimal, and the report warns that totals may not reach 100, so the tolerance is 0.5. A misread digit, such as India's 20-24 total read as `10.1` for `10.7`, fails it.
* A total lies between its parts. Each Total is a weighted mean of its Males and Females (or Rural and Urban) columns, so it lies between them, within 0.1 for rounding.

`tests/test_srs_statistical_report.py` compares every value with `tests/fixtures/srs_stat/expected.csv`, read from `pdftotext -layout`, then changes single cells and checks that each rule fails on them.
