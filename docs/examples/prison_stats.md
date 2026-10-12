---
description: "NCRB's Prison Statistics India 2023 read with a recipe: jail capacity, inmates and occupancy rate by State/UT, by sex and by jail type, with a table split over three pages joined by its printed column numbers and checked against its own totals."
---

# Prison Statistics India

The National Crime Records Bureau (NCRB) publishes Prison Statistics India each year. Chapter 1 of the [2023 report](https://www.ncrb.gov.in/uploads/files/PSI-2023.pdf) compares jail capacity with inmates on 31st December; the occupancy rate is inmates per 100 places. Two tables give it by State/UT:

* Table 1.2 (page 58 of the report): available capacity, inmate population and occupancy rate, each for men (M), women (F), transgender inmates (Tr.) and the total; columns (3) to (14).
* Table 1.3 (pages 59-61): the same by jail type (Central, District, Sub, Women, Borstal School, Open, Special and Other jails, then the total), three columns each. Its columns (3)-(11), (12)-(20) and (21)-(29) run over three pages: `Table – 1.3`, `(Continued)` and `(Concluded)`.

Rows follow NCRB's usual layout (Crime in India, ADSI): 28 States, `TOTAL (STATES)`, 8 UTs, `TOTAL (UTs)`, `TOTAL (ALL-INDIA)`, under a row of printed column numbers.

The files are in `examples/prison_stats/`: `recipe.toml` and `psi.py`. The fixture is pages 58-61 of the 2023 report, in `tests/fixtures/prison_stats/`.

## The recipe

```toml
name = "Prison Statistics India: jail capacity and occupancy"

[pages]
match = '(?m)Table\s*[–-]\s*1\.[23]\s*(\(Con|$)'

[engines]
ocr = false

[parser]
type = "custom"
function = "psi.py:parse"
key = ["page", "row", "col"]

# M + F + Tr = Total (Table 1.2); the eight jail types add up to Total (Table 1.3)
[[checks]]
column = "group"
rule = "Total = rest"
by = ["table", "row", "measure"]
where = "measure != 'occupancy'"

[[checks]]
column = "row"
rule = "totalstates = rest"
by = ["page", "col"]
where = "(section == 'state' or row == 'totalstates') and measure != 'occupancy'"

[[checks]]
column = "row"
rule = "totaluts = rest"
by = ["page", "col"]
where = "(section == 'ut' or row == 'totaluts') and measure != 'occupancy'"

[[checks]]
column = "row"
rule = "totalallindia = totalstates + totaluts"
by = ["page", "col"]
where = "measure != 'occupancy'"

# Table 1.3's Total columns repeat Table 1.2's
[[checks]]
column = "table"
rule = "1.3 = 1.2"
by = ["row", "measure"]
where = "group == 'Total'"

[[checks]]
function = "psi.py:occupancy"

[output]
layout = "table"
rows = ["state"]
columns = "column"
format = "csv"
```

The chapter's text also cites "Table 1.2" and "Table - 1.3 showing ...", so `match` wants the title alone on its line or followed by `(Continued)` or `(Concluded)`.

A cell is keyed by page, State/UT and printed column number. `psi.py` names each column (`capacity_f`, `district_inmates`, `all_occupancy`) and adds the `table`, `group` (sex or jail type) and `measure` columns the checks group by. The three pages of Table 1.3 join on the State/UT, so the output has one row per State/UT.

## Run it

```bash
pdfexorcist extract https://www.ncrb.gov.in/uploads/files/PSI-2023.pdf --recipe examples/prison_stats/recipe.toml -o psi.csv
```

On the whole report `match` picks pages 58-61, the fixture's pages:

```bash
pdfexorcist extract tests/fixtures/prison_stats/psi_2023_p58-61.pdf --recipe examples/prison_stats/recipe.toml -o psi.csv
```

```
  pdftotext   1,521 readings  0.0s
  pdfplumber  1,521 readings  0.2s
  pymupdf     1,521 readings  0.0s
  camelot     1,521 readings  4.8s
  pdfium      1,521 readings  0.0s

Agreed        1,521  100.0% of cells
Unresolved        0
Checks      6 rules  all passed

Wrote psi.csv (table layout, 39 rows).
```

```
state,section,capacity_m,capacity_f,capacity_tr,capacity,...,occupancy,central_capacity,...,all_inmates,all_occupancy
ANDHRA PRADESH,state,7901,930,0,8831,...,89.3,3764,...,7889,89.3
...
DELHI,ut,9346,680,0,10026,...,200.2,9346,...,20077,200.2
...
TOTAL (ALL-INDIA),total,408327,30679,113,439119,...,120.8,198150,...,530333,120.8
```

The report prints `-` for an occupancy rate with no capacity behind it (Lakshadweep's women, most States' transgender inmates), and the output keeps it. The 2022 report reads the same way, every cell agreed and every check passing.

## The parser

`parse()` in `psi.py`, in outline (pseudocode):

```text
def parse(pages):
    for page_no, lines in pages:
        find the row of column numbers "(1) (2) (3) ..."; none -> this engine abstains on the page
        table = "1.2" if the last column is (14) else "1.3"
        for each line below it with one value per column:
            name = the label without its serial number ("1 ANDHRA PRADESH" -> "ANDHRA PRADESH")
            yield {"page", "row": name in lower-case letters, "col": printed column number,
                   "state": name, "section": state | ut | total, "table", "group", "measure",
                   "column", "value"}
            stop after TOTAL (ALL-INDIA)
```

On one page camelot sets each State's name on a line above its values; a line with no values holds the name for the next one.

## The checks

* Totals add up across a row: M + F + Tr. = Total in Table 1.2, for capacity and inmates; the eight jail types add up to the Total in Table 1.3, which ties its three pages together.
* States add up to `TOTAL (STATES)`, UTs to `TOTAL (UTs)`, and the two to `TOTAL (ALL-INDIA)`, in each count column.
* Table 1.3's Total columns equal Table 1.2's: capacity, inmates and occupancy for each State/UT.
* Occupancy = 100 × inmates / capacity, to the printed 0.1, for every sex and jail type with a capacity above 0. Delhi's 20,077 inmates in 10,026 places print as 200.2.

`tests/test_prison_stats.py` compares every value with `tests/fixtures/prison_stats/expected.csv`, read from `pdftotext -layout`, and checks that misreading Delhi's 20077 inmates as 20777 fails four rules.
