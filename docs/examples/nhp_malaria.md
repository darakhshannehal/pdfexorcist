---
description: "CBHI's National Health Profile 2023 read with a recipe: State/UT wise malaria cases and deaths for 2018-2022, the provisional year marked in the column names, and a check that the States and UTs add up to India."
---

# NHP malaria cases and deaths

The Central Bureau of Health Intelligence (CBHI) publishes the National Health Profile each year. Table 3.1.1 of [NHP 2023](https://cbhidghs.mohfw.gov.in/sites/default/files/2024-09/Final-Central-Bureau-of-Health-Intelligene-July-2024.pdf), on page 120 of the PDF, gives malaria cases and deaths by State/UT for 2018-2022, from NCVBDC (whose monthly counts are in the [MMIS report](mmis.md)). The 2022 header reads `2022 (till Dec-Prov.)`.

The files are in `examples/nhp_malaria/`: `recipe.toml` and `nhp_malaria.py`. The fixture is page 120 of the report, in `tests/fixtures/nhp/`.

## The recipe

```toml
name = "NHP malaria cases and deaths"

[pages]
# skips the contents page, which repeats the title
match = 'Deaths due to Malaria in India.{0,300}Cases\s+Deaths'

[engines]
ocr = false

[parser]
type = "custom"
function = "nhp_malaria.py:parse"
key = ["page", "state", "col"]

# the States and UTs add up to India, in each year and measure
[[checks]]
column = "state"
rule = "India = rest"
by = ["page", "col"]
name = "States/UTs add up to India"

[output]
layout = "table"
rows = ["state"]
columns = "col"
format = "csv"
```

`match` also asks for the `Cases Deaths` header row, since the contents page repeats the title. On the whole report it keeps page 120 only.

A cell is keyed by State/UT and column, `2018 Cases` to `2022 (Prov.) Deaths`. The parser reads the years from the header. The printed serial number goes in `sno`; India and Daman & Diu have none.

## Run it

```bash
pdfexorcist extract https://cbhidghs.mohfw.gov.in/sites/default/files/2024-09/Final-Central-Bureau-of-Health-Intelligene-July-2024.pdf --recipe examples/nhp_malaria/recipe.toml -o nhp.csv
```

The whole report gives the same table as the fixture:

```bash
pdfexorcist extract tests/fixtures/nhp/nhp_2023_p120.pdf --recipe examples/nhp_malaria/recipe.toml -o nhp.csv
```

```
  pdftotext   374 readings  0.0s
  pdfplumber  374 readings  0.1s
  pymupdf     374 readings  0.0s
  camelot     374 readings  1.5s
  pdfium      374 readings  0.0s

Agreed         374  100.0% of cells
Unresolved       0
Checks      1 rule  all passed

Wrote nhp.csv (table layout, 38 rows).
```

```
state,sno,2018 Cases,2018 Deaths,2019 Cases,2019 Deaths,2020 Cases,2020 Deaths,2021 Cases,2021 Deaths,2022 (Prov.) Cases,2022 (Prov.) Deaths
India,,429928,96,338494,77,186532,93,161753,90,173975,64
Andhra Pradesh,1,6040,0,3104,0,2027,0,1315,0,2019,0
...
Chattisgarh,5,78717,39,60458,31,36667,34,29733,38,30028,11
...
Andaman & Nicobar Islands,29,259,0,202,0,85,2,27,0,46,0
Chandigarh,30,44,0,22,0,7,0,6,0,1,0
Dadra & Nagar Haveli,31,221,1,73,0,40,0,54,0,39,0
Daman & Diu,,24,0,8,0,,,,,,
...
Puducherry,36,54,1,21,0,15,0,5,0,0,0
```

## The parser

`parse()` in `nhp_malaria.py`, in outline (pseudocode):

```text
def parse(pages):
    for page_no, lines in pages:
        the first line with "State" and three or more years  -> the header
            each year, "2022 (Prov.)" when "(till" follows it
        each later line: label, then its values
            "29 Andaman & Nicobar" followed by "Islands" (no values) -> one name
            "<serial> <name>" -> sno, state
            values pair up with (year, Cases), (year, Deaths) from the left
            -> yield {"page", "state", "col": "2018 Cases", ..., "sno", "year", "measure", "value"}
```

Four engines read `Andaman & Nicobar` and `Islands` as two lines and camelot as one cell; joining the wrapped line gives every engine the same name. Daman & Diu has values for 2018 and 2019 only, before it merged with Dadra & Nagar Haveli, so its four values fill the first four columns.

## The check

States/UTs = India, in each of the ten columns. Every column adds up exactly, so the run exits with code 0.

The check passes when two rows swap values. In 2021 Uttar Pradesh has 13 cases and Uttarakhand 10792, the reverse of their 2020 and 2022 sizes. The output keeps them as printed.

`tests/test_nhp_malaria.py` compares every value with `tests/fixtures/nhp/expected.csv`, built from `pdftotext -layout` with a regular expression, and checks that changing India's 2021 cases by one fails that column alone.
