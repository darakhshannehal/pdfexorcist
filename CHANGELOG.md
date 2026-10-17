# Changelog

All notable changes to pdfexorcist are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[PEP 440](https://peps.python.org/pep-0440/) (`1.2.0`, `1.2.0rc1`).

Add each change under [Unreleased] as you make it. The Prepare release
workflow moves those entries into a dated section.

## [Unreleased]

### Added

- IMI Coverage Evaluation Survey 2018 example (`examples/imi_ces/`), also on the web
- Examples for NCRB Prison Statistics India (`examples/prison_stats/`), the SRS Statistical Report (`examples/srs_statistical_report/`), the SRS maternal mortality bulletin and Cause of Death report (`examples/srs_maternal_mortality/`), MoRTH Road Accidents in India (`examples/road_accidents/`) and the CBHI National Health Profile's malaria table (`examples/nhp_malaria/`)
- The web version lets you choose which engines read an uploaded PDF
- Make web examples RESTful
- `placement="both"` (`parse_by_columns`, recipe `[parser]`): a value counts only where its order and x agree; else the cell is unresolved
- `pages.find(pdf, pattern)` and `extract --pages-matching REGEX`; pages without text are matched by OCR of their top strip
- Type3 fonts without a Unicode map are decoded by tesseract; `extract(decode_fonts=False)` turns it off
- Built-in check `lossy value` fails `2E+05`, `#####` and `#REF!`
- CRS State Table 6 and District Tables 7-10 examples, also on the web

### Fixed

- Slanted text across a table ("Not Available") is dropped so it cannot chain rows
- Fake bold (text drawn 3-4 times) is read once by pdfplumber, pymupdf, pdfium, camelot and pdftotext
- pdftotext splits narrow-column values joined by one space
- PDFium reads Type3 fonts with oversized glyph boxes
- A cell every engine read two values for is unresolved, not dropped
- Sideways tables on upright pages (no `/Rotate`) are turned upright
- mypy error in `_upright.py`

## [0.1.2 - 11 Oct 2026]

### Added

- MMIS example (`examples/mmis_malaria/`): NCVBDC's monthly malaria report
- Opt-in engines `pypdf` (extra `pypdf`), `pdfjs` (Mozilla pdf.js through Node) and `doctr` (docTR models on onnxruntime, extra `doctr`)
- camelot tries its network, hybrid and ml flavors too; ml needs extra `camelot-ml`
- The web version runs `pypdf` and `pdfjs`

### Changed

- camelot needs camelot-py 2 or later
- camelot drops tables nested in a larger one, so network and hybrid do not count a row twice

### Fixed

- `is_value` accepts Excel's scientific display of a too-wide number (`2E+05`)
- `--jobs` frees each engine's pages once parsed

## [0.1.1 - 4 Oct 2026]

### Added

Initial release:
- pdfexorcist also runs in the browser (`web/`) with pyodide at <https://pdfexorcist.in/>
- pdfexorcist is a new package for extracting tables from pdfs (text and scanned)

