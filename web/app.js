// previews run in their own worker so they never wait behind an extraction

import { Client } from './client.js';
import { bytes, get, kept, keptWasm, manifest } from './net.js';
import { outcome } from './results.js';
import { button, draw, el, failure, fill, fmt, minutes, plural } from './ui.js';

const $ = (id) => document.getElementById(id);
const MAX_BYTES = 200e6; 
const LONG = 20; 
const SECONDS_PER_PAGE = 1.8; 


const starting = () => ({ ready: false, failed: null, pause: true, status: 'Loading the engines…', since: performance.now() });
let engines = starting();
const BOOT = 'boot-seconds'; // last start-up from the cache
let lastBoot = 0;
try {
  lastBoot = Number(localStorage.getItem(BOOT)) || 0;
} catch {}
const files = manifest();
// The page compiles pdfium one time for the two workers.
// The page gets pdfium first, so that the previews do not wait for the engine download.
const pdfium = files.then((m) => {
  const url = Object.fromEntries(m);
  return Promise.all([keptWasm(url['vendor/pdfium.wasm']), kept(url['vendor/pdfium.cjs']).then((b) => new TextDecoder().decode(b))]);
});
const init = () => pdfium.then(([m, script]) => ({ pdfium: m, script }));

const worker = new Client('./worker.js', {
  init,
  onStatus: (data) => {
    if (data.type === 'restart') engines = starting();
    else if (data.type === 'download') engines = { ...engines, download: data };
    else if (data.type === 'status') {
      // true when the cache did not have the engines at the start of this visit
      engines = { ...engines, status: `${data.text}…`, downloading: engines.downloading || data.downloading };
    }
    else if (data.type === 'ready') {
      if (!engines.downloading) {
        try {
          localStorage.setItem(BOOT, Math.round((performance.now() - engines.since) / 1000));
        } catch {}
      }
      engines = { ...engines, ready: true, pause: data.pause, names: data.names, later: data.later, optIn: data.optIn };
      pickers();
    }
    else if (data.type === 'failed') engines = { ...engines, failed: `The engines could not start: ${data.message}` };
    showEngines();
  },
});
const previewer = new Client('./preview.js', { init });

function showEngines() {
  const dots = $('dots');
  dots.className = `dots ${engines.ready ? 'ready' : engines.failed ? '' : 'busy'}`;
  $('engine-status').textContent = engines.failed
    ? engines.failed
    : engines.ready && !engines.pause
      ? 'Ready, without pdftotext: it needs Chrome 137, Safari 27 or Firefox 153, and does not run on iPhone or iPad.'
      : engines.ready
        ? `Ready: ${engines.names.join(', ')}${more().length ? `; under Options: ${more().join(', ')}` : ''}.`
        : engineStatus();
}
showEngines();
// download messages redraw on their own
const ticker = lastBoot && setInterval(() => (engines.ready || engines.failed ? clearInterval(ticker) : showEngines()), 1000);

const mb = (n) => Math.round(n / 1e6);

function engineStatus() {
  const d = engines.download;
  if (d && d.loaded < d.total) {
    const left = d.eta === null ? '' : `, about ${took(d.eta * 1000)} left`;
    return `Downloading the engines: ${mb(d.loaded)} of ${mb(d.total)} MB${left}. This browser keeps them for later visits.`;
  }
  const left = lastBoot - (performance.now() - engines.since) / 1000;
  return engines.downloading || left < 1 ? engines.status : `${engines.status} About ${took(left * 1000)} left.`;
}

const more = () => [...engines.later, ...engines.optIn];

function pickers() {
  const was = new Map([...$('engine-picks').querySelectorAll('input')].map((c) => [c.value, c.checked]));
  fill($('engine-picks'), engineBoxes((name) => was.get(name) ?? engines.names.includes(name)));
}
const picked = (box = $('engine-picks')) => [...box.querySelectorAll('input:checked')].map((c) => c.value);

function engineBoxes(checked) {
  return [...engines.names, ...more()].map((name) =>
    el('label', {}, el('input', { type: 'checkbox', value: name, checked: checked(name) }), name,
      engines.later.includes(name) ? el('small', {}, ' (downloads once)') : ''));
}


async function firstPage(pdf, width) {
  const { doc } = await previewer.ask({ open: pdf });
  try {
    const { pages } = await previewer.ask({ doc, first: 0, max: 1, width });
    return draw(pages[0]);
  } finally {
    previewer.ask({ close: doc });
  }
}

// a sample loads when its card nears the screen, or when it is opened
const thumbs = new Map();
const nearScreen = new IntersectionObserver(
  (entries) => entries.forEach((e) => {
    if (!e.isIntersecting) return;
    nearScreen.unobserve(e.target);
    thumbs.get(e.target)();
  }),
  { rootMargin: '400px 0px' },
);

function addExample(ex) {
  const name = ex.pdf.split('/').pop();
  let pdf;
  const load = () => (pdf ??= bytes(`samples/${name}`));
  const thumb = el('span', { className: 'thumb' });
  const open = async () => run({ id: ex.id, kicker: ex.kicker, title: ex.title, pdf: await load(), name, recipe: ex.recipe });
  openers.set(ex.id, open);
  const card = el('li', {}, button('example', open,
    thumb,
    el('span', {},
      el('span', { className: 'kicker' }, ex.kicker),
      el('span', { className: 'title' }, ex.title),
      el('span', { className: 'blurb' }, ex.blurb)),
    el('span', { className: 'go', ariaHidden: 'true' }, '→')));
  $('examples').append(card);
  thumbs.set(card, () => load().then((p) => firstPage(p, 224)).then((canvas) => thumb.append(canvas)).catch(() => {}));
  nearScreen.observe(card);
}

// each example has its own link, #<id>; any other hash is the home page
const openers = new Map();
let shown; // id of the example whose result is on the work view
function route() {
  const id = decodeURIComponent(location.hash.slice(1));
  if (id && id === shown) return show('work'); // back to it: no second read
  const open = openers.get(id);
  if (open) return open();
  show('home');
}

get('examples.json')
  .then((r) => r.json())
  .then((list) => list.forEach(addExample))
  .then(route);

files
  .then((list) => {
    for (const [path] of list) {
      if (path.startsWith('examples/') && path.endsWith('.toml')) {
        $('recipe').append(el('option', { value: path }, path.slice('examples/'.length)));
      }
    }
  });

const file = $('file');
file.onchange = () => file.files[0] && openFile(file.files[0]);
const drop = $('drop');
drop.ondragover = (e) => {
  e.preventDefault();
  drop.classList.add('over');
};
drop.ondragleave = () => drop.classList.remove('over');
drop.ondrop = (e) => {
  e.preventDefault();
  drop.classList.remove('over');
  const f = [...e.dataTransfer.files].find((f) => /\.pdf$/i.test(f.name) || f.type === 'application/pdf');
  if (f) openFile(f);
};

async function openFile(f) {
  if (f.size > MAX_BYTES) {
    $('engine-status').textContent = `${f.name} is ${mb(f.size)} MB. The limit here is ${mb(MAX_BYTES)} MB; the command-line tool has none.`;
    return;
  }
  const chosen = engines.ready ? picked() : undefined;
  if (chosen?.length === 0) { // an empty --engines would run the defaults
    $('engine-status').textContent = 'Pick the engines to run under Options.';
    return;
  }
  const pdf = new Uint8Array(await f.arrayBuffer());
  run({
    kicker: 'Your PDF',
    title: f.name,
    pdf,
    name: f.name,
    recipe: $('recipe').value || undefined,
    pages: $('pages').value.trim() || undefined,
    engines: chosen,
  });
  file.value = '';
}

// ---- views

function show(view) {
  $('home').hidden = view !== 'home';
  $('work').hidden = view !== 'work';
  $(view).classList.remove('fade');
  void $(view).offsetWidth;
  $(view).classList.add('fade');
  window.scrollTo({ top: 0 });
}
$('back').onclick = () => {
  history.pushState(null, '', './');
  show('home');
};
window.onpopstate = route;

let active = null; // the run on screen; a new one aborts it

async function run(job) {
  active?.abort();
  const { signal } = (active = new AbortController());
  const hash = job.id ? `#${encodeURIComponent(job.id)}` : '#result';
  if (location.hash !== hash) history.pushState(null, '', hash);
  shown = job.id;
  show('work');
  $('doc-kicker').textContent = job.kicker;
  $('doc-title').textContent = job.title;
  fill($('result')); // else the previous result shows under the new title
  const pane = pagesPane(job.pdf, signal);
  let count;
  try {
    count = await pane.ready;
  } catch (e) {
    if (!signal.aborted) fill($('result'), failure('This file could not be opened as a PDF.', e.message));
    return;
  }
  if (signal.aborted) return;
  job = { ...job, count, doc: workerCopy(job, signal) };
  pane.pick = (page) => read({ ...job, pages: String(page), sample: false }, pane, signal);
  if (job.pages || count <= LONG) return read(job, pane, signal);
  const pick = (pages) => read({ ...job, pages, sample: Boolean(pages) }, pane, signal);
  const own = el('input', { placeholder: 'e.g. 12-15', ariaLabel: 'Pages to read', inputMode: 'numeric' });
  fill($('result'),
    el('p', { className: 'say' }, `${fmt(count)} pages.`),
    el('p', { className: 'sub' },
      `All of them take about ${minutes(count * SECONDS_PER_PAGE)} here. Try five first. For many long PDFs, the `,
      el('a', { href: 'cli/' }, 'command-line tool'), ' is faster.'),
    el('div', { className: 'actions' },
      button('button', () => pick('1-5'), 'Read pages 1–5'),
      button('button quiet', () => pick(undefined), `Read all ${fmt(count)} pages`)),
    el('form', { className: 'pick', onsubmit: (e) => (e.preventDefault(), own.value.trim() && pick(own.value.trim())) },
      el('label', {}, 'Other pages ', own),
      el('button', { className: 'button quiet', type: 'submit' }, 'Read')));
}

/** opened once per engine worker; closed when the run ends */
function workerCopy(job, signal) {
  let held = null; // {generation, doc}
  signal.addEventListener('abort', () => {
    if (held?.generation === worker.generation) held.doc.then((doc) => worker.ask({ close: doc })).catch(() => {});
  });
  return () => {
    if (held?.generation !== worker.generation) {
      held = { generation: worker.generation, doc: worker.ask({ open: job.pdf, name: job.name }).then((r) => r.doc) };
    }
    return held.doc;
  };
}

async function read(job, pane, signal) {
  const result = $('result');
  const stop = new AbortController();
  const view = progressView(() => {
    stop.abort();
    worker.restart(new Error('stopped'));
  });
  fill(result, view.node);
  const started = performance.now();
  let first; // the first page read; the estimate leaves out the engines' start-up
  const progress = (data) => {
    if (!data.downloading) first ??= performance.now();
    view.update(data);
  };
  try {
    const doc = await job.doc();
    const res = await worker.ask({ doc, recipe: job.recipe, pages: job.pages, engines: job.engines }, { signal: AbortSignal.any([signal, stop.signal]), progress });
    if (res.cancelled) return;
    const pagesRead = res.summary.pages?.length || job.count;
    const again = job.sample
      ? { read: () => read({ ...job, pages: undefined, sample: false }, pane, signal),
          seconds: ((performance.now() - (first ?? started)) / 1000 / pagesRead) * job.count }
      : null;
    fill(result,
      outcome(res, job, (performance.now() - started) / 1000, pane, again, (page) => openGrid(job, page)),
      rerun(job, pane, signal));
  } catch (e) {
    if (signal.aborted) return;
    fill(result, stop.signal.aborted ? failure('Stopped.', 'The engines are restarting.') : failure('Something went wrong.', e.message));
  } finally {
    view.done();
  }
}

/** A form that reads the same pages again with other engines. The engines of the last run are checked. */
function rerun(job, pane, signal) {
  const ran = job.engines ?? engines.names;
  const box = el('div', { className: 'engine-boxes' }, engineBoxes((name) => ran.includes(name)));
  const again = (e) => {
    e.preventDefault();
    const chosen = picked(box);
    if (chosen.length) read({ ...job, engines: chosen }, pane, signal);
  };
  return el('form', { className: 'picks rerun', onsubmit: again },
    el('p', { className: 'sub' }, 'Read again with other engines. More engines, more cross-checks; camelot is the slowest.'),
    box,
    el('div', { className: 'actions' }, el('button', { className: 'button quiet', type: 'submit' }, 'Read again')));
}

/** a tab opened now, inside the click, so pop-up blockers allow it; filled when ready */
async function openGrid(job, page) {
  const tab = window.open('', '_blank');
  if (!tab) return;
  tab.document.title = `Page ${page}`;
  tab.document.body.textContent = `Drawing the grid for page ${page}…`;
  try {
    const { html } = await worker.ask({ show: await job.doc(), page, recipe: job.recipe, engines: job.engines });
    tab.location = URL.createObjectURL(new Blob([html], { type: 'text/html' }));
  } catch (e) {
    tab.document.body.textContent = e.message;
  }
}

/** ready resolves to the page count; pages render as they scroll into view */
function pagesPane(pdf, signal) {
  const pane = $('pages-view');
  fill(pane, el('p', { className: 'more' }, 'Opening the PDF…'));
  const opened = previewer.ask({ open: pdf });
  const figures = [];
  let queue = Promise.resolve(); // serialised: one PDFium document
  const render = (i) => {
    const f = figures[i];
    if (f.rendered) return f.rendered;
    f.rendered = queue = queue
      .then(async () => {
        const { doc } = await opened;
        const { pages } = await previewer.ask({ doc, first: i, max: 1, width: 900 }, { signal });
        f.firstChild.replaceWith(draw(pages[0]));
      })
      .catch(() => {});
    return f.rendered;
  };
  const observer = new IntersectionObserver(
    (entries) => entries.forEach((e) => e.isIntersecting && render(Number(e.target.dataset.i))),
    { root: pane, rootMargin: '1200px 0px' },
  );
  signal.addEventListener('abort', () => {
    observer.disconnect();
    opened.then(({ doc }) => previewer.ask({ close: doc })).catch(() => {});
  });
  const ready = opened.then(({ count }) => {
    for (let i = 0; i < count; i++) {
      const caption = el('figcaption', {}, `Page ${i + 1}`, button('link', () => api.pick?.(i + 1), 'Read this page'));
      const f = el('figure', {}, el('div', { className: 'slot' }), caption);
      f.dataset.i = i;
      figures.push(f);
    }
    fill(pane, figures);
    figures.forEach((f) => observer.observe(f));
    return count;
  });
  ready.catch(() => !signal.aborted && fill(pane, el('p', { className: 'more' }, 'No preview.')));
  const api = {
    pick: null, // set once the run can read; reads one page
    ready,
    async show(n) {
      const f = figures[n - 1];
      if (!f) return;
      f.scrollIntoView({ behavior: 'smooth', block: 'start' });
      await render(n - 1);
      f.classList.add('flash');
      setTimeout(() => f.classList.remove('flash'), 1600);
    },
  };
  return api;
}

/** 0.4 s, 12 s, 2:05 */
function took(ms) {
  const s = ms / 1000;
  if (s < 10) return `${s.toFixed(1)} s`;
  const whole = Math.round(s);
  return whole < 60 ? `${whole} s` : mmss(whole);
}

const mmss = (s) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;

function progressView(onStop) {
  const rows = new Map(); // a row appears as each engine starts
  const list = el('ul', { className: 'progress' });
  const status = el('p', { className: 'sub' });
  const clock = el('span', {});
  const started = performance.now();
  const tick = () => {
    const s = Math.round((performance.now() - started) / 1000);
    clock.textContent = mmss(s);
    status.textContent = engines.ready ? '' : `${engineStatus()} Reading starts when they are ready.`;
  };
  tick();
  const timer = setInterval(tick, 1000);
  const stop = button('button quiet', onStop, 'Stop');
  return {
    node: el('div', { className: 'running' },
      el('p', { className: 'say' }, 'Reading… ', clock),
      status,
      list,
      el('div', { className: 'actions' }, stop)),
    update({ engine, page, pages, downloading }) {
      let row = rows.get(engine);
      if (!row) {
        row = el('li', {}, el('b', {}, engine), el('span', {}), el('i', { className: 'meter' }));
        rows.set(engine, row);
        list.append(row);
      }
      if (downloading) {
        row.children[1].textContent = 'downloading, once: kept for later visits';
        return;
      }
      row.started ??= performance.now(); // the engine starts to read now
      const time = took(performance.now() - row.started);
      row.children[1].textContent = page >= pages
        ? `${plural(pages, 'page')}, done in ${time}`
        : `page ${fmt(page + 1)} of ${fmt(pages)}, ${time}`;
      row.children[2].style.setProperty('--done', pages ? page / pages : 1);
      row.classList.toggle('done', page >= pages);
    },
    done: () => clearInterval(timer),
  };
}

// ---- theme

$('theme').onclick = () => {
  const root = document.documentElement;
  const dark = root.dataset.theme
    ? root.dataset.theme === 'dark'
    : matchMedia('(prefers-color-scheme: dark)').matches;
  root.dataset.theme = dark ? 'light' : 'dark';
  try {
    localStorage.setItem('theme', root.dataset.theme);
  } catch {}
};
