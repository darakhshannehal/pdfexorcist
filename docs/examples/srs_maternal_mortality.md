---
description: "The SRS Special Bulletin on Maternal Mortality 2021-23 read with a recipe: MMR by State with its 95% confidence interval split into two columns, lifetime risk as a number, and checks from the bulletin's own definitions. Plus the top 10 causes of death from the companion Cause of Death report."
---

# SRS maternal mortality

The Registrar General of India's 4-page [Special Bulletin on Maternal Mortality in India 2021-23](https://censusindia.gov.in/nada/index.php/catalog/46177/download/50425) comes from the Sample Registration System (SRS). Table 1 on page 3 gives, for India, 19 States, the other States together and three subtotals, the Maternal Mortality Ratio (MMR, maternal deaths per 100,000 live births) with its 95% confidence interval, the Maternal Mortality Rate (per 100,000 women aged 15-49) and the lifetime risk. Table 2 on page 4 gives the age distribution of maternal and non-maternal deaths, also with intervals.

The files are in `pdfexorcist/recipes/srs_maternal_mortality/`: `recipe.toml` (Table 1), `age.toml` (Table 2), `cod_top10.toml` (see [below](#the-cause-of-death-report)), and the parsers `srs_mmr.py` and `srs_cod_top10.py`. The fixtures are the whole bulletin and one page of the Cause of Death report, in `tests/fixtures/srs_mmr/`.

## Intervals and percents

A row of Table 1 prints as

```
INDIA                         88          (79,96)        5         0.18%
```

`VALUE` in `pdfexorcist/rows.py` reads `(79,96)` as one parenthesised number with a thousands comma, so the default parser would vote on the interval as one string. `srs_mmr.py` splits it into `mmr_lower` and `mmr_upper`, and drops the `%` from the lifetime risk, whose column is `lifetime_risk_pct`.

PDFium splits a few tokens at glyph gaps: `0.18 %`, `(18,26 )`, `30 - 34`. The parser joins a lone `%` or `)` to the token before it and closes up a hyphen between digits.

## The recipe

```toml
name = "SRS maternal mortality by State"

[pages]
match = 'Table 1: Maternal Mortality Ratio'

[engines]
ocr = false

[parser]
type = "custom"
function = "srs_mmr.py:parse"
key = ["page", "row", "column"]

[[checks]]
function = "srs_mmr.py:within_ci"

# Lifetime risk = 1 - (1 - rate/100000)^35, from the bulletin's paragraph 5
[[checks]]
function = "srs_mmr.py:lifetime_risk"

[output]
layout = "table"
rows = ["area"]
columns = "column"
format = "csv"
```

`age.toml` is the same with `match = 'Table 2: Age Distribution'` and only the interval check.

## Run it

```bash
pdfexorcist extract tests/fixtures/srs_mmr/srs_mmr_bulletin_2021-23.pdf --recipe pdfexorcist/recipes/srs_maternal_mortality/recipe.toml -o mmr.csv
```

```
✓ pdftotext   120 readings  0.0s
✓ pdfplumber  120 readings  0.1s
✓ pymupdf     120 readings  0.0s
✓ camelot     120 readings  0.5s
✓ pdfium      120 readings  0.0s

✓  Agreed          120  100.0% of cells
   Unresolved        0
✓  Checks      2 rules  all passed
```

```
area,mmr,mmr_lower,mmr_upper,mortality_rate,lifetime_risk_pct
INDIA,88,79,96,5,0.18
Assam,110,53,167,6,0.23
...
EAG AND ASSAM SUBTOTAL,118,103,133,9,0.31
...
OTHER SUBTOTAL,75,62,88,4,0.14
```

`age.toml` reads Table 2, every cell agreed:

```
area,maternal_pct,maternal_lower,maternal_upper,non_maternal_pct,non_maternal_lower,non_maternal_upper
15-19,4,2,6,8,8,9
...
15-49,100,,,100,,
```

The 15-49 total prints no interval, so those cells are empty.

## The parser

`parse()` in `srs_mmr.py`, in outline (pseudocode):

```text
def parse(pages):
    for page_no, lines in pages:
        for line in lines:
            tokens = mend PDFium splits, then split on spaces
            label, values = leading words, trailing numbers and intervals
            values shaped  n (lo,hi) n p%      -> Table 1: mmr, mmr_lower, mmr_upper, mortality_rate, lifetime_risk_pct
            values shaped  p% (lo,hi) p% (lo,hi) -> Table 2: maternal_pct, ..., non_maternal_upper
            values shaped  p% p%               -> Table 2 total row
            "SUBTOTAL" after a label-only line  -> join them: "EAG AND ASSAM SUBTOTAL"
            -> yield {"page", "row", "area", "column", "value"}
```

The parser picks the table from the shape of the values. Four engines read the first subtotal as two lines, `EAG AND ASSAM` and `SUBTOTAL`, and camelot as one cell; joining them gives every engine the same row key.

## The checks

* The estimate lies inside its 95% CI, for the MMR in Table 1 and for both proportions in Table 2.
* Lifetime risk matches the Maternal Mortality Rate. The bulletin defines lifetime risk as 1 - (1 - rate/100000)^35. The rate is printed as a whole number, so the check allows the risk the formula gives for rate ± 0.5, plus half a unit in the last printed place. Kerala (rate 1, risk 0.05%) sits near the edge.

Both checks pass on every row.

## The Cause of Death report

`cod_top10.toml` reads Table 2.3A of the companion [SRS Cause of Death Statistics 2021-23](https://censusindia.gov.in/nada/index.php/catalog/46176/download/50424) (page 31 of the PDF): the top 10 causes of death in India, as shares of deaths for males, females and persons.

```bash
pdfexorcist extract tests/fixtures/srs_mmr/srs_cod_2021-23_p31.pdf --recipe pdfexorcist/recipes/srs_maternal_mortality/cod_top10.toml -o cod.csv
```

```
rank,cause,male,female,person
1,Cardiovascular diseases,32.4,29.1,31.0
2,Respiratory infections,8.9,9.9,9.3
...
other,All Other Remaining Causes,17.6,15.2,16.6
```

The whole report gives the same output, every cell agreed. Rows are keyed by rank because causes 7 and 10 wrap onto a second line that only camelot joins; `cause` takes the majority reading, the first line. Each sex's eleven shares must add up to 100 within rounding.

`tests/test_srs_maternal_mortality.py` compares all three tables with the `expected*.csv` files in `tests/fixtures/srs_mmr/`, checked against `pdftotext -layout`.
