// each engine's lines, and pdfexorcist charts, on every fixture: Pyodide vs native

import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { nodeBoot, ROOT } from '../node-boot.mjs';

const DUMP = join(ROOT, 'web/test/dump_lines.py');
const [{ stdout }, { py }] = await Promise.all([
  promisify(execFile)('uv', ['run', 'python', DUMP, ROOT], {
    cwd: ROOT,
    maxBuffer: 1 << 30,
    env: { ...process.env, PDFEXORCIST_PDFJS: join(ROOT, 'web/node_modules/pdfjs-dist') }, // the site's pdf.js
  }),
  nodeBoot(),
]);
const native = JSON.parse(stdout);
py.FS.writeFile('/tmp/dump_lines.py', readFileSync(DUMP));
const web = JSON.parse(
  await py.runPythonAsync(`
import contextlib, io, runpy, sys
sys.argv = ['dump_lines.py', '/repo']
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    runpy.run_path('/tmp/dump_lines.py', run_name='__main__')
buf.getvalue()`),
);
// x may drift for non-embedded fonts: native PDFium uses system fonts
const texts = (v) => (Array.isArray(v) ? v.map(([p, ls]) => [p, ls.map((l) => l.map(([, t]) => t))]) : v);
const lines = (v) => (Array.isArray(v) ? texts(v).flatMap(([p, ls]) => ls.map((l) => `${p} ${JSON.stringify(l)}`)) : [String(v)]);
let bad = 0;
let drifted = 0;
let drift = 0;
for (const k of Object.keys(native)) {
  if (JSON.stringify(native[k]) === JSON.stringify(web[k])) continue;
  if (JSON.stringify(texts(native[k])) !== JSON.stringify(texts(web[k]))) {
    bad++;
    console.log('TEXT DIFFERS', k);
    const [a, b] = [native[k], web[k]].map(lines);
    const i = a.findIndex((l, j) => l !== b[j]);
    console.log('  native', a[i]?.slice(0, 150));
    console.log('  web   ', b[i]?.slice(0, 150));
    continue;
  }
  drifted++;
  native[k].forEach(([, ls], i) =>
    ls.forEach((l, j) =>
      l.forEach(([x], c) => {
        drift = Math.max(drift, Math.abs(x - web[k][i][1][j][c][0]));
      }),
    ),
  );
  console.log('x drifts', k);
}
const n = Object.keys(native).length;
console.log(`${n - bad - drifted} of ${n} engine readings identical, ${drifted} identical in text`
  + ` with x off by at most ${drift.toFixed(3)} pt, ${bad} differ in text`);

// charts read paths, not engine lines: the CSV must match byte for byte
const CHARTS = join(ROOT, 'web/test/dump_charts.py');
const nativeCharts = JSON.parse((await promisify(execFile)('uv', ['run', 'python', CHARTS, ROOT], { cwd: ROOT, maxBuffer: 1 << 28 })).stdout);
py.FS.writeFile('/tmp/dump_charts.py', readFileSync(CHARTS));
const webCharts = JSON.parse(
  await py.runPythonAsync(`
import contextlib, io, runpy, sys
sys.argv = ['dump_charts.py', '/repo']
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    runpy.run_path('/tmp/dump_charts.py', run_name='__main__')
buf.getvalue()`),
);
let chartsBad = 0;
for (const k of new Set([...Object.keys(nativeCharts), ...Object.keys(webCharts)])) {
  if (JSON.stringify(nativeCharts[k]) === JSON.stringify(webCharts[k])) continue;
  chartsBad++;
  const [a, b] = [nativeCharts[k], webCharts[k]].map((v) => (v ? v[0].split('\n') : []));
  const i = a.findIndex((l, j) => l !== b[j]);
  console.log('CHARTS DIFFER', k, `\n  native ${a[i]}\n  web    ${b[i]}`);
}
const m = Object.keys(nativeCharts).length;
console.log(`${m - chartsBad} of ${m} fixtures with charts read identically`);
process.exit(bad || chartsBad ? 1 : 0);
