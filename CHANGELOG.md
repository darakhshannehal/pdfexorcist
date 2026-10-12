# Changelog

All notable changes to pdfexorcist are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[PEP 440](https://peps.python.org/pep-0440/) (`1.2.0`, `1.2.0rc1`).

Add each change under [Unreleased] as you make it. The Prepare release
workflow moves those entries into a dated section.

## [Unreleased]

### Added

- IMI Coverage Evaluation Survey 2018 example (`examples/imi_ces/`), also on the web
- Make web examples RESTful

### Fixed

- Tables printed sideways on an upright page (no `/Rotate`) are turned upright before feeding into the engines

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
- pdfexorcist also runs in the browser (`web/`) with pyodide! at <https://saketkc.github.io/pdfexorcist/>:
- pdfexorcist is a new package for extracting tables from pdfs (both text and scanned ones) 

