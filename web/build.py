"""Assemble the site: the browser app at the root, the Sphinx docs under cli/.

    python web/build.py site          # after: sphinx-build -b html docs site/cli
    python web/build.py --manifest    # what Pyodide gets, as [path, source] JSON

It also writes files.json: the path, content-versioned URL and size of each file,
and recipes.json: the short name and name of each shipped recipe.
It also writes a redirect at the old address of each docs page.
"""

import hashlib
import json
import shutil
import sys
import urllib.request
from pathlib import Path

WEB = Path(__file__).resolve().parent
ROOT = WEB.parent
RECIPES = ROOT / "pdfexorcist" / "recipes"
APP = [
    "index.html",
    "app.js",
    "client.js",
    "ui.js",
    "results.js",
    "worker.js",
    "preview.js",
    "pdfium.js",
    "net.js",
    "core.js",
    "engines.js",
    "examples.json",
]
VENDOR = ["pdftotext.js", "pdftotext.wasm", "pdfium.cjs", "pdfium.wasm"]
LICENSES = ["pdftotext.COPYING", "pdftotext.COPYING3", "pdfium.LICENSE"]  # GPL: ship them
WHEELS = Path.home() / ".cache" / "pdfexorcist-web" / "wheels"
ASSETS = {
    "favicon.svg": "docs/assets/favicon.svg",
    "logo.svg": "docs/assets/logo/logo.svg",
    "social-preview.png": "docs/assets/logo/social-preview.png",
}
REDIRECT = """<!doctype html>
<meta charset="utf-8">
<title>Moved</title>
<link rel="canonical" href="{to}">
<meta http-equiv="refresh" content="0; url={to}">
<p>This page moved to <a href="{to}">{to}</a>.</p>
"""


def _copy(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dest)


def fetch_wheels(dest: Path) -> list[Path]:
    """wheels.json's wheels in dest, each sha256-checked."""
    out = []
    for w in json.loads((WEB / "wheels.json").read_text()):
        path = dest / w["url"].rsplit("/", 1)[1]
        if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != w["sha256"]:
            with urllib.request.urlopen(w["url"]) as r:
                data = r.read()
            got = hashlib.sha256(data).hexdigest()
            if got != w["sha256"]:
                sys.exit(f"{w['url']}: sha256 {got}, expected {w['sha256']}")
            dest.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        out.append(path)
    return out


def python_files() -> list[tuple[str, Path]]:
    """(path in Pyodide's file system, source) for everything boot() installs."""
    package = sorted(p for p in (ROOT / "pdfexorcist").iterdir() if p.suffix in (".py", ".mjs"))
    out = [(f"site/{p.relative_to(ROOT)}", p) for p in package]
    out += [(f"site/{p.name}", p) for p in sorted((WEB / "py").glob("*.py"))]
    for d in ("vendor", "pymupdf"):
        out += [(f"wheel/{p.name}", p) for p in sorted((WEB / d).glob("*.whl"))]
    out += [(f"wheel/{p.name}", p) for p in fetch_wheels(WHEELS)]
    # recipes go in the package, as in the wheel; samples load on demand
    out += [
        (f"site/{p.relative_to(ROOT)}", p)
        for p in sorted(RECIPES.rglob("*"))
        if p.suffix in (".toml", ".py") and "__pycache__" not in p.parts
    ]
    return out


def recipe_names() -> list[list[str]]:
    """[short name, name] of each shipped recipe, for the page's recipe picker."""
    import importlib.util

    import tomllib

    # by file: importing the package would need its dependencies
    spec = importlib.util.spec_from_file_location("_shipped", ROOT / "pdfexorcist" / "_shipped.py")
    shipped = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(shipped)
    out = []
    for p in shipped.shipped_recipes():  # loaded from the repo, so these are its recipes
        short = shipped.recipe_name(p)
        out.append([short, tomllib.loads(p.read_text(encoding="utf-8")).get("name") or short])
    return out


def _entry(path: str, url: str, src: Path) -> list:
    """Return a files.json entry: [path, versioned url, size]."""
    return [path, _versioned(url, src), src.stat().st_size]


def _versioned(url: str, src: Path) -> str:
    """Return url?v=<content hash>.

    net.js kept stores each version in the browser after the first download.
    """
    return f"{url}?v={hashlib.sha256(src.read_bytes()).hexdigest()[:16]}"


def _redirects(site: Path) -> int:
    """Redirects from the docs' old addresses."""
    n = 0
    for page in (site / "cli").rglob("*.html"):
        rel = page.relative_to(site / "cli")
        old = site / rel
        if rel == Path("index.html"):  # the app
            continue
        depth = len(rel.parts) - 1
        to = "../" * depth + "cli/" + rel.as_posix()
        old.parent.mkdir(parents=True, exist_ok=True)
        old.write_text(REDIRECT.format(to=to))
        n += 1
    return n


def main(site: Path) -> None:
    if not (site / "cli" / "index.html").exists():
        sys.exit(
            f"{site}/cli/index.html is missing: build the docs first (sphinx-build ... {site}/cli)"
        )
    for name in APP:
        _copy(WEB / name, site / name)
    for name in VENDOR + LICENSES:
        _copy(WEB / "vendor" / name, site / "vendor" / name)
    for name, src in ASSETS.items():
        _copy(ROOT / src, site / "assets" / name)
    manifest = []
    for path, src in python_files():
        _copy(src, site / "py" / path)
        manifest.append(_entry(path, f"py/{path}", src))
    # Pyodide does not use these files.
    # The page and the workers use this list to get them by content.
    kept = [n for n in VENDOR if not n.endswith(".js")]  # worker.js imports pdftotext.js directly
    manifest += [_entry(f"vendor/{n}", f"vendor/{n}", WEB / "vendor" / n) for n in kept]
    (site / "files.json").write_text(json.dumps(manifest))
    (site / "recipes.json").write_text(json.dumps(recipe_names()))
    for ex in json.loads((WEB / "examples.json").read_text()):
        _copy(ROOT / ex["pdf"], site / "samples" / Path(ex["pdf"]).name)
    (site / ".nojekyll").touch()  # else Pages hides Sphinx's _static
    n = len(manifest) - len(kept)
    print(f"Wrote the app to {site}/ ({n} Python files), {_redirects(site)} redirects")


if __name__ == "__main__":
    if sys.argv[1:2] == ["--manifest"]:  # for node-boot.mjs
        print(json.dumps([[path, str(src)] for path, src in python_files()]))
    else:
        main(Path(sys.argv[1] if len(sys.argv) > 1 else "site"))
