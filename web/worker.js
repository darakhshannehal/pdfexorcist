// in: {open: pdf, name} -> {doc}; {doc, recipe, pages} -> extract(); {show: doc, page} -> {html}; {close: doc}

import { boot, close, extract, open, show } from './core.js';
import { canPause, emscriptenProgram, pdfjsProgram } from './engines.js';
import { bytes, get, wasm } from './net.js';
import { serve } from './pdfium.js';
import Pdftotext from './vendor/pdftotext.js';

const PYODIDE = 'https://cdn.jsdelivr.net/pyodide/v314.0.7/full/pyodide.mjs';
const PDFJS = 'https://cdn.jsdelivr.net/npm/pdfjs-dist@6.4.299/legacy/build';
const status = (text) => postMessage({ type: 'status', text });

async function pythonFiles() {
  const manifest = await (await get('files.json')).json();
  return Object.fromEntries(await Promise.all(manifest.map(async ([path, url]) => [path, await bytes(url)])));
}

async function start() {
  status('Downloading the engines');
  const files = pythonFiles(); // not awaited; see core.js interpreter
  // keeps only this file's bytes, not every file's, for the life of the worker
  const script = files.then((f) => f['site/pdfexorcist/_pdfjs.mjs']);
  // opt-in engine: pdf.js is fetched on its first run; pdfjsWorker set runs it in this thread
  const pdfjs = async () => {
    globalThis.pdfjsWorker ??= await import(`${PDFJS}/pdf.worker.mjs`);
    const url = URL.createObjectURL(new Blob([await script], { type: 'text/javascript' }));
    return Promise.all([import(`${PDFJS}/pdf.mjs`), import(url)]);
  };
  const [{ loadPyodide }, module] = await Promise.all([import(PYODIDE), wasm('vendor/pdftotext.wasm'), pdfium]);
  const programs = { pdftotext: emscriptenProgram(Pdftotext, module), node: pdfjsProgram(pdfjs) };
  return boot({ loadPyodide, programs, files, log: status });
}

// [default engines, opt-in engines this build can run]
const ENGINES = `
from pdfexorcist.doctor import all_status
[[s.name for s in all_status() if s.installed and s.default == d] for d in (True, False)]
`;

const pdfium = serve(answer, (id) => cancelled.add(id));
const env = start();
env.then(
  ({ py }) => {
    const [names, optIn] = py.runPython(ENGINES).toJs();
    postMessage({ type: 'ready', pause: canPause(), names, optIn });
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
    if (msg.show) return [await show(await env, { ...msg, doc: msg.show })];
    return [await extract(await env, { ...msg, progress })];
  });
  queue = job.catch(() => {});
  return job;
}
