# pdfexorcist in the browser

# pdfexorcist-web

The WASM version of pdfexorcist through `pyodide`.

By default, it runs pdftotext, pdfplumber, pymupdf and pdfium. It runs camelot, `pypdf` and `pdfjs`
only when you select them. The page downloads the camelot wheels and opencv when you first select
camelot. pdf.js runs in the page, and the page loads it when you first select it.

The browser keeps each file in Cache Storage with its content hash. Thus, the next visit downloads
only the files that changed. The OCR engines cannot run, because they must have native libraries that
Pyodide does not have.

## Run and check

```bash
npm install                                    
node test/pytest.mjs -q                        
node test/parity.mjs                           
sphinx-build -b html docs site/cli && python web/build.py site
python -m http.server -d site 8765            
node test/site.mjs http://127.0.0.1:8765/    
```

