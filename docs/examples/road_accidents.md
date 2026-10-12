---
description: "MoRTH's Road Accidents in India 2022 read with a recipe: three State/UT tables printed sideways, with three-level headers, Indian comma grouping, blank and placeholder cells, a neighbouring page drawn off each page, and checks that the States add up to the Total, shares match counts and ranks match the 2022 counts."
---

# Road Accidents in India 2022

The Ministry of Road Transport and Highways (MoRTH) compiles [Road Accidents in India](https://morth.nic.in/sites/default/files/RA_2022_30_Oct.pdf) each year from State/UT police records. The site blocks some downloaders; a [mirror](https://www.acma.in/uploads/otherdocmanager/RA_2022_30_Oct.pdf) has the same file. Annexures 2-4 (pages 136-138) give accidents, persons killed and persons injured by State/UT for 2019-2022, with each State's share and rates per lakh population, per 10,000 vehicles and per 10,000 km of road.

The tables are printed sideways on portrait pages with no `/Rotate` flag. The header has three levels (`State/UT-Wise Total Number of Road Accidents during` / `2022` / `Number`, `Rank`), then a row of column numbers, 1 to 18. Counts use Indian grouping (`1,58,984`). Some cells are blank or hold a placeholder: Ladakh has `NA` for 2019 and 2020 and a rank only for persons injured, Daman & Diu is merged into Dadra & Nagar Haveli from 2020 (`$`), and Telangana has no population for 2019 and 2020 (`#`).

The files are in `examples/road_accidents/`: `recipe.toml` and `morth.py`. The fixture is pages 136-138 of the report, in `tests/fixtures/road_accidents/`.

## The recipe

```toml
name = "MoRTH Road Accidents in India 2022"

[pages]
match = 'Road Accidents in India:\s*2019\s*to\s*2022'
fit_boxes = false

[engines]
ocr = false

[normalize]
remove_commas = true  # Indian grouping: 1,58,984

[parser]
type = "custom"
function = "morth.py:parse"
key = ["table", "state", "column"]

[[checks]]
column = "state"
rule = "total = rest"
by = ["table", "column"]
where = "column in ['2019', '2020', '2021', '2022']"
name = "States/UTs add up to the Total"

[[checks]]
function = "morth.py:share"

[[checks]]
function = "morth.py:rank"

[output]
layout = "table"
rows = ["measure", "name"]
columns = "column"
format = "csv"
```

`match` keeps the three annexure pages. pdfexorcist turns them upright before the engines read them.

The report was laid out as spreads: pages 136 and 137 each carry the other's table outside the page box. pdfexorcist grows a page box over such text by default, which would put both tables on both pages. With `fit_boxes = false` only camelot still reads the neighbour, and the parser drops a table it has already read.

A cell is keyed by table, State/UT and column. camelot misses the titles, so tables are numbered in reading order (1 accidents, 2 killed, 3 injured) and `measure`, read from the title by the other four engines, is an extra column. `name` is the State/UT as printed.

## Run it

```bash
pdfexorcist extract https://morth.nic.in/sites/default/files/RA_2022_30_Oct.pdf --recipe examples/road_accidents/recipe.toml -o ra.csv
```

The whole report and the fixture give the same table:

```bash
pdfexorcist extract tests/fixtures/road_accidents/morth_ra_2022_annexure_p136-138.pdf --recipe examples/road_accidents/recipe.toml -o ra.csv
```

```
  pdftotext   1,774 readings  0.0s
  pdfplumber  1,774 readings  0.4s
  pymupdf     1,774 readings  0.0s
  camelot     1,774 readings  16.6s
  pdfium      1,774 readings  0.1s

Agreed         1,774  100.0% of cells
Unresolved         0
Failed checks      1  agreed values that break a rule
  x share is not 100 x count / Total: 1 cell

Wrote ra.csv (table layout, 114 rows).
```

```
measure,name,2019,2020,2021,2022,rank_2022,share_2019,...,per_lakh_pop_2022,per_10k_vehicles_2019,per_10k_vehicles_2020,per_10k_km_roads_2019
accidents,Andhra Pradesh,21992,19509,21556,21249,9,4.8,...,40.1,18.3,14.9,1247.1
...
killed,Telangana,6964,6882,7557,7559,10,4.4,...,19.9,5.7,5.3,495.5
killed,Daman & Diu,28,$,$,$,,0.0,...,,,,1022.3
killed,Ladakh,NA,NA,56,62,,,...,20.7,,,
killed,Total,158984,138383,153972,168491,,100,...,12.2,5.3,4.2,292.7
...
injured,Total,449360,346747,384448,443366,,100,...,32.2,15.1,10.6,827.3
```

The `per_10k_km_roads` column is headed 2019 in all three tables, as printed.

## The parser

`parse()` in `morth.py`, in outline (pseudocode):

```text
def parse(pages):
    for each line:
        "Total Number of <Road Accidents|Persons Killed|Persons Injured> in"  -> the measure
        "1 2 3 ... 18"                                                     -> a new table
        "<S.No> <State/UT> <values>" ... "Total <values>"                  -> its rows
    at "Total": skip the table if this reading already had it, else
        column centres = the median x of each value over rows with all 16 values
        each value (or "#", "$") -> the nearest column, never before the previous one
        yield {"table", "state", "column", "value" without commas, "name", "measure"}
```

Placing values by x keeps blank cells blank: Ladakh's killed row has no rank and no 2019 or 2020 share, so its first share, `0.0`, lands under 2021. pdftotext sometimes joins two values into one cell (`21.6 39.9`, Andhra Pradesh's injured per lakh population for 2020 and 2021). Such a cell fills the two adjacent columns nearest its x, and its row sets no centres.

## The checks

* States/UTs add up to the Total in each of 2019-2022, in all three tables. Every one adds up exactly.
* Share = 100 × count / Total, to the printed 0.1. One cell fails: Lakshadweep's 2022 share of persons injured prints as 0.1, but 2 of 4,43,366 is 0.0. The output keeps it as printed, and the run exits with code 1 and lists it in `ra.review.csv`.
* Rank: the 2022 rank is 1 + the number of States/UTs with a larger 2022 count. All ranks pass.

`tests/test_road_accidents.py` compares the table with `tests/fixtures/road_accidents/expected.csv`, checked against `pdftotext -layout`.
