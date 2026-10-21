// in: {open: pdf, name} -> {doc}; {doc, recipe, pages, engines} -> extract(); {show: doc, page} -> {html}; {close: doc}
// {charts: doc, pages} -> charts()
// engines: the names of the engines to run. If there is no list, the worker uses the engines installed at boot.
// The worker downloads each LATER engine in the list before the run.

import { add, boot, charts, close, extract, LATER, laterEngine, open, show } from './core.js';
import { canPause, emscriptenProgram, pdfjsProgram } from './engines.js';
import { kept, keptWasm, manifest, missing, prune } from './net.js';
import { serve } from './pdfium.js';
import Pdftotext from './vendor/pdftotext.js';

const PYODIDE = 'https://cdn.jsdelivr.net/pyodide/v314.0.7/full/pyodide.mjs';
const PDFJS = 'https://cdn.jsdelivr.net/npm/pdfjs-dist@6.4.299/legacy/build';
const status = (text, downloading) => postMessage({ type: 'status', text, downloading });

const files = manifest();
const urls = files.then((m) => Object.fromEntries(m));
const fetchKept = async (path, got) => kept((await urls)[path], got);

const PDFTOTEXT = 'vendor/pdftotext.wasm';
/** The files that boot installs: all Python files, but not the files of the LATER engines. */
const pythonPaths = (entries) => entries.map(([p]) => p).filter((p) => !p.startsWith('vendor/') && !laterEngine(p));

async function pythonFiles(paths, got) {
  return Object.fromEntries(await Promise.all(paths.map(async (p) => [p, await fetchKept(p, got)])));
}

/** Returns got(n) for bytes(); posts {loaded, total, eta} at most 4 times a second. */
function meter(total) {
  const start = performance.now();
  let loaded = 0;
  let sent = 0;
  return (n) => {
    loaded += n;
    const now = performance.now();
    if (loaded < total && now - sent < 250) return;
    sent = now;
    const rate = loaded / (now - start); // bytes per ms
    const eta = now - start > 1000 ? Math.max(0, (total - loaded) / rate / 1000) : null; // the first chunks give a bad rate
    postMessage({ type: 'download', loaded, total, eta });
  };
}

async function start() {
  await pdfium; // The page sends pdfium first. Thus, the previews do not share the network with the download below.
  const entries = await files;
  const paths = pythonPaths(entries);
  const sizes = Object.fromEntries(entries.map(([, u, size]) => [u, size]));
  const url = await urls;
  const need = await missing([...paths, PDFTOTEXT].map((p) => url[p])); // the page gets pdfium itself
  const total = need.reduce((sum, u) => sum + sizes[u], 0);
  status(need.length ? 'Downloading the engines' : 'Starting the engines', need.length > 0);
  const got = meter(total);
  prune(entries.map(([, u]) => u)).catch(() => {}); // removes the files that are not in files.json
  const python = pythonFiles(paths, got); // not awaited; see core.js interpreter
  // keeps only this file's bytes, not every file's, for the life of the worker
  const script = python.then((f) => f['site/pdfexorcist/_pdfjs.mjs']);
  // opt-in engine: pdf.js is fetched on its first run; pdfjsWorker set runs it in this thread
  const pdfjs = async () => {
    globalThis.pdfjsWorker ??= await import(`${PDFJS}/pdf.worker.mjs`);
    const url = URL.createObjectURL(new Blob([await script], { type: 'text/javascript' }));
    return Promise.all([import(`${PDFJS}/pdf.mjs`), import(url)]);
  };
  const [{ loadPyodide }, module] = await Promise.all([import(PYODIDE), urls.then((u) => keptWasm(u[PDFTOTEXT], got)), pdfium]);
  const programs = { pdftotext: emscriptenProgram(Pdftotext, module), node: pdfjsProgram(pdfjs) };
  return boot({ loadPyodide, programs, files: python, log: status });
}

// [default engines, opt-in engines that this build can run].
// The lists do not include a LATER engine until add() installs it.
const ENGINES = `
from pdfexorcist.doctor import all_status
[[s.name for s in all_status() if s.installed and s.default == d] for d in (True, False)]
`;
// The engines for a run that gives no list. These are the engines installed at boot.
// Thus, an engine that add() installs does not change the examples.
let defaults;

const pdfium = serve(answer, (id) => cancelled.add(id));
const env = start();
env.then(
  ({ py }) => {
    const [names, optIn] = py.runPython(ENGINES).toJs();
    defaults = names;
    postMessage({ type: 'ready', pause: canPause(), names, later: Object.keys(LATER), optIn });
  },
  (e) => postMessage({ type: 'failed', message: String(e?.message ?? e) }),
);

const cancelled = new Set(); // queued extractions whose run moved on
let queue = Promise.resolve(); // serialised: one Python interpreter

function answer(msg) {
  if (msg.open) return env.then((e) => [{ doc: open(e, { pdf: msg.open, name: msg.name }) }]);
  if (msg.close) return env.then((e) => [close(e, msg.close)]);
  const job = queue.then(async () => {
    if (cancelled.delete(msg.id)) return [{ cancelled: true }];
    const progress = (engine, page, pages) => postMessage({ type: 'progress', id: msg.id, engine, page, pages });
    const ctx = await env;
    if (msg.charts) return [await charts(ctx, { doc: msg.charts, pages: msg.pages })]; // runs no engines
    const engines = msg.engines ?? defaults;
    const downloading = (engine) => postMessage({ type: 'progress', id: msg.id, engine, downloading: true });
    await add(ctx, engines, Object.keys(await urls), fetchKept, downloading);
    if (msg.show) return [await show(ctx, { ...msg, engines, doc: msg.show })];
    return [await extract(ctx, { ...msg, engines, progress })];
  });
  queue = job.catch(() => {});
  return job;
}
