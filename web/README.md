# pdfexorcist in the browser

# pdfexorcist-web

The WASM version of pdfexorcist through `pyodide`.

It runs the five default text engines (pdftotext, pdfplumber, pymupdf, pdfium, camelot) and the
opt-in `pypdf` and `pdfjs`. pdf.js runs in the page and loads on first use. The OCR engines need
native libraries Pyodide lacks.

## Run and check

```bash
npm install                                    
node test/pytest.mjs -q                        
node test/parity.mjs                           
sphinx-build -b html docs site/cli && python web/build.py site
python -m http.server -d site 8765            
node test/site.mjs http://127.0.0.1:8765/    
```

