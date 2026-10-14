// in: {open: pdf, name} -> {doc}; {doc, recipe, pages, engines} -> extract(); {show: doc, page} -> {html}; {close: doc}
// engines: the names of the engines to run. If there is no list, the worker uses the engines installed at boot.
// The worker downloads each LATER engine in the list before the run.

import { add, boot, close, extract, LATER, laterEngine, open, show } from './core.js';
import { canPause, emscriptenProgram, pdfjsProgram } from './engines.js';
import { allKept, kept, keptWasm, manifest, prune } from './net.js';
import { serve } from './pdfium.js';
import Pdftotext from './vendor/pdftotext.js';

const PYODIDE = 'https://cdn.jsdelivr.net/pyodide/v314.0.7/full/pyodide.mjs';
const PDFJS = 'https://cdn.jsdelivr.net/npm/pdfjs-dist@6.4.299/legacy/build';
const status = (text, downloading) => postMessage({ type: 'status', text, downloading });

const urls = manifest().then((m) => Object.fromEntries(m));
const fetchKept = async (path) => kept((await urls)[path]);

/** The files that boot installs: all Python files, but not the files of the LATER engines. */
async function pythonFiles() {
  const paths = Object.keys(await urls).filter((p) => !p.startsWith('vendor/') && !laterEngine(p));
  return Object.fromEntries(await Promise.all(paths.map(async (p) => [p, await fetchKept(p)])));
}

async function start() {
  await pdfium; // The page sends pdfium first. Thus, the previews do not share the network with the download below.
  const entries = Object.entries(await urls);
  const now = entries.filter(([p]) => !laterEngine(p)).map(([, u]) => u);
  const cold = !(await allKept(now));
  status(cold ? 'Downloading the engines' : 'Starting the engines', cold);
  prune(entries.map(([, u]) => u)).catch(() => {}); // removes the files that are not in files.json
  const files = pythonFiles(); // not awaited; see core.js interpreter
  // keeps only this file's bytes, not every file's, for the life of the worker
  const script = files.then((f) => f['site/pdfexorcist/_pdfjs.mjs']);
  // opt-in engine: pdf.js is fetched on its first run; pdfjsWorker set runs it in this thread
  const pdfjs = async () => {
    globalThis.pdfjsWorker ??= await import(`${PDFJS}/pdf.worker.mjs`);
    const url = URL.createObjectURL(new Blob([await script], { type: 'text/javascript' }));
    return Promise.all([import(`${PDFJS}/pdf.mjs`), import(url)]);
  };
  const [{ loadPyodide }, module] = await Promise.all([import(PYODIDE), urls.then((u) => keptWasm(u['vendor/pdftotext.wasm'])), pdfium]);
  const programs = { pdftotext: emscriptenProgram(Pdftotext, module), node: pdfjsProgram(pdfjs) };
  return boot({ loadPyodide, programs, files, log: status });
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
    const engines = msg.engines ?? defaults;
    const downloading = (engine) => postMessage({ type: 'progress', id: msg.id, engine, downloading: true });
    await add(ctx, engines, Object.keys(await urls), fetchKept, downloading);
    if (msg.show) return [await show(ctx, { ...msg, engines, doc: msg.show })];
    return [await extract(ctx, { ...msg, engines, progress })];
  });
  queue = job.catch(() => {});
  return job;
}
