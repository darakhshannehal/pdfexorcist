// node test/site.mjs http://127.0.0.1:8765/ [screenshot dir]; CHROME overrides the path

import { execFile, execFileSync } from 'node:child_process';
import { copyFileSync, mkdirSync, mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { promisify } from 'node:util';
import { chromium } from 'playwright-core';

const ROOT = fileURLToPath(new URL('../..', import.meta.url));
const examples = JSON.parse(readFileSync(join(ROOT, 'web/examples.json'), 'utf8'));

// The default engines of the site. Camelot downloads only when you select it (core.js LATER).
const WEB_ENGINES = ['pdftotext', 'pdfplumber', 'pymupdf', 'pdfium'];

async function native(ex, engines = WEB_ENGINES) {
  const dir = mkdtempSync(join(tmpdir(), 'site-'));
  try {
    copyFileSync(join(ROOT, ex.pdf), join(dir, 'doc.pdf'));
    if (ex.charts) {
      const args = ['run', 'pdfexorcist', 'charts', join(dir, 'doc.pdf'), '-o', join(dir, 'doc.csv'), '--json'];
      const { points, charts } = JSON.parse((await promisify(execFile)('uv', args, { cwd: ROOT })).stdout);
      return { cells: { points, charts }, csv: readFileSync(join(dir, 'doc.csv'), 'utf8') };
    }
    let out;
    try {
      const args = ['run', 'pdfexorcist', 'extract', join(dir, 'doc.pdf'), '--recipe', ex.recipe, '--json', '-q', '--engines', engines.join(',')];
      out = (await promisify(execFile)('uv', args, { cwd: ROOT })).stdout;
    } catch (e) {
      out = e.stdout; // exit 1 when a check fails
    }
    const { total, verified, unresolved, failed_checks } = JSON.parse(out).cells;
    return { cells: { verified, total, unresolved, failed_checks }, csv: readFileSync(join(dir, 'doc.csv'), 'utf8') };
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

const url = process.argv[2] ?? 'http://127.0.0.1:8765/';
const shots = process.argv[3];
const CHROME = process.env.CHROME ?? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
if (shots) mkdirSync(shots, { recursive: true });

async function longPdf(page) {
  const dir = mkdtempSync(join(tmpdir(), 'site-'));
  try {
    const pdf = join(dir, 'long.pdf');
    execFileSync('uv', ['run', 'python', '-c', `
import pymupdf
src = pymupdf.open(${JSON.stringify(join(ROOT, examples[0].pdf))})
out = pymupdf.open()
while out.page_count < 99: out.insert_pdf(src)
out.save(${JSON.stringify(pdf)})`], { cwd: ROOT });
    await page.locator('#file').setInputFiles(pdf);
    await page.waitForSelector('text=99 pages.');
    await page.waitForSelector('#pages-view figure'); // the count arrives before pages
    await page.locator('#pages-view figure[data-i="23"]').scrollIntoViewIfNeeded(); // pages render on scroll
    await page.waitForSelector('#pages-view figure[data-i="23"] canvas');
    await page.locator('text=Read pages 1–5').click();
    await page.waitForSelector('.progress li.done', { timeout: 300_000 });
    await page.waitForSelector('#result .say >> text=/values agreed/', { timeout: 300_000 });
    const sub = (await page.locator('#result .sub').allInnerTexts()).join(' ');
    console.log(`long PDF, pages 1-5: ${await page.locator('#result .say').innerText()} ${sub}`);
    if (!sub.includes('Pages 1-5')) failures.push('long PDF: the sample did not read pages 1-5');
    await page.locator('.alert.calm >> text=Read all 99 pages').click();
    await page.waitForSelector('.progress li >> text=/page \\d+ of 99/', { timeout: 300_000 });
    await page.locator('text=Stop').click();
    await page.waitForSelector('#result .say >> text=Stopped.');
    await page.waitForSelector('#dots.ready', { state: 'attached', timeout: 300_000 });
    console.log('long PDF: Stop worked and the engines came back');
    await page.locator('#back').click();
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

async function slowFirstVisit(browser) {
  const context = await browser.newContext({ viewport: { width: 1360, height: 900 } });
  try {
    const page = await context.newPage();
    const cdp = await context.newCDPSession(page);
    await cdp.send('Network.enable');
    // At 4 Mbit/s, approximately 60 MB of engines download in 2 minutes. A thumbnail uses approximately 1 MB.
    await cdp.send('Network.emulateNetworkConditions', {
      offline: false, latency: 40, downloadThroughput: 4e6 / 8, uploadThroughput: 1e6 / 8,
    });
    await page.goto(url);
    await page.locator('#examples .thumb canvas').first().waitFor({ timeout: 20_000 }).catch(() => {});
    const drawn = await page.locator('#examples .thumb canvas').count();
    const ready = await page.locator('#dots.ready').count();
    console.log(`slow first visit: ${drawn} thumbnails drawn after 20 s, engines ${ready ? 'ready' : 'still loading'}`);
    if (!drawn) failures.push('slow first visit: no thumbnail within 20 s; previews wait behind the engine download');
  } finally {
    await context.close();
  }
}

async function withCamelot(page) {
  const ex = examples[0];
  const want = native(ex, [...WEB_ENGINES, 'camelot']);
  await page.locator('.example').first().click();
  await page.waitForSelector('#result .say >> text=/values agreed/', { timeout: 300_000 });
  await page.locator('.rerun input[value=camelot]').check();
  await page.locator('.rerun button[type=submit]').click();
  await page.waitForSelector('.progress li >> text=/downloading/', { timeout: 60_000 });
  await page.waitForSelector('#result .say >> text=/values agreed/', { timeout: 300_000 });
  const voters = await page.locator('.voters li').count();
  const csv = await downloaded(page, 'text=Download CSV');
  console.log(`${ex.title}, read again with camelot: ${await page.locator('#result .say').innerText()} | ${voters} engines`);
  if (voters !== WEB_ENGINES.length + 1) failures.push(`with camelot: ${voters} engines ran`);
  if (csv !== (await want).csv) failures.push('with camelot: CSV differs from the CLI with five engines');
  await page.locator('#back').click();
}

async function secondVisit(context) {
  const page = await context.newPage();
  const fetched = [];
  const files = await (await fetch(new URL('files.json', url))).json();
  const kept = new Set(files.map(([, u]) => new URL(u, url).href)); // the files in files.json, not the Pyodide files
  context.on('request', (r) => kept.has(r.url()) && fetched.push(r.url())); // this includes the requests of the workers
  await page.goto(url);
  const said = await page.locator('#engine-status').innerText();
  await page.waitForSelector('#dots.ready', { state: 'attached', timeout: 300_000 });
  console.log(`second visit: "${said}", ${fetched.length} engine files fetched`);
  if (/Downloading|MB/.test(said)) failures.push(`second visit: says "${said}"`); // "MB" is in the text of the first visit
  if (fetched.length) failures.push(`second visit fetched ${fetched.length} engine files, e.g. ${fetched[0]}`);
  await page.close();
}

const natives = examples.map((ex) => native(ex)); // these runs occur while Chrome starts the engines

async function chartsExample(page, i) {
  await page.waitForSelector('#result .say >> text=/points from/', { timeout: 300_000 });
  const say = await page.locator('#result .say').innerText();
  const num = (re) => Number((say.match(re)?.[1] ?? '0').replaceAll(',', ''));
  const web = { points: num(/^([\d,]+) points/), charts: num(/from ([\d,]+) charts?/) };
  const want = await natives[i];
  const csv = await downloaded(page, 'text=Download CSV');
  const tables = await page.locator('#result table').count();
  console.log(`${examples[i].title}: ${say} | ${tables} tables\n  browser ${JSON.stringify(web)}\n  native  ${JSON.stringify(want.cells)}`);
  console.log(`  CSV ${csv === want.csv ? 'identical to' : 'DIFFERS from'} the CLI's (${csv.length} bytes)`);
  if (new URL(page.url()).hash !== `#${examples[i].id}`) failures.push(`example ${i}: URL is ${page.url()}`);
  if (JSON.stringify(web) !== JSON.stringify(want.cells)) failures.push(`example ${i}: counts differ from the CLI`);
  if (tables !== want.cells.charts) failures.push(`example ${i}: ${tables} tables for ${want.cells.charts} charts`);
  if (csv !== want.csv) failures.push(`example ${i}: CSV differs from the CLI`);
  if (shots) await page.screenshot({ path: `${shots}/example-${i}.png`, fullPage: true });
  await page.locator('#back').click();
}
const browser = await chromium.launch({ executablePath: CHROME });
const downloaded = async (page, button) => {
  const [d] = await Promise.all([page.waitForEvent('download'), page.locator(button).click()]);
  return readFileSync(await d.path(), 'utf8');
};
const failures = [];
try {
  await slowFirstVisit(browser);
  // a different context, so that secondVisit can open one more page in the same profile
  const context = await browser.newContext({ colorScheme: 'light', viewport: { width: 1360, height: 900 }, acceptDownloads: true });
  const page = await context.newPage();
  page.on('pageerror', (e) => failures.push(`page error: ${e.message}`));
  page.on('console', (m) => m.type() === 'error' && failures.push(`console: ${m.text()}`));
  await page.goto(url);
  await page.waitForFunction(
    () => document.querySelector('#dots.ready') || /could not start/.test(document.querySelector('#engine-status').textContent),
    null,
    { timeout: 600_000 },
  );
  if (!(await page.locator('#dots.ready').count())) throw new Error(await page.locator('#engine-status').innerText());
  for (const card of await page.locator('#examples li').all()) { // thumbnails load as cards scroll near
    await card.scrollIntoViewIfNeeded();
    await card.locator('.thumb canvas').waitFor();
  }
  await page.evaluate(() => window.scrollTo(0, 0));
  if (shots) await page.screenshot({ path: `${shots}/home-light.png`, fullPage: true });
  for (let i = 0; i < examples.length; i++) {
    await page.locator('.example').nth(i).click();
    if (examples[i].charts) {
      await chartsExample(page, i);
      continue;
    }
    await page.waitForSelector('#result .say >> text=/values agreed/', { timeout: 300_000 });
    await page.waitForSelector('#pages-view canvas');
    const say = await page.locator('#result .say').innerText();
    const sub = (await page.locator('#result .sub').allInnerTexts()).join(' ');
    const rows = await page.locator('#result table').first().locator('tbody tr').count();
    const voters = await page.locator('.voters li').count();
    const num = (re, text) => Number((text.match(re)?.[1] ?? '0').replaceAll(',', ''));
    const all = num(/^All ([\d,]+) values agreed/, say);
    const web = {
      verified: all || num(/^([\d,]+) of/, say),
      total: all || num(/of ([\d,]+) values/, say),
      unresolved: num(/([\d,]+) without agreement/, say),
      failed_checks: num(/([\d,]+) values? failed/, sub),
    };
    const want = await natives[i];
    console.log(`${examples[i].title}: ${say} ${sub} | ${rows} table rows | ${voters} engines`);
    const csv = await downloaded(page, 'text=Download CSV');
    console.log(`  browser ${JSON.stringify(web)}\n  native  ${JSON.stringify(want.cells)}`);
    console.log(`  CSV ${csv === want.csv ? 'identical to' : 'DIFFERS from'} the CLI's (${csv.length} bytes)`);
    if (new URL(page.url()).hash !== `#${examples[i].id}`) failures.push(`example ${i}: URL is ${page.url()}`);
    if (voters !== WEB_ENGINES.length) failures.push(`example ${i}: ${voters} engines ran`);
    if (!rows) failures.push(`example ${i}: the table is empty`);
    if (JSON.stringify(web) !== JSON.stringify(want.cells)) failures.push(`example ${i}: counts differ from the CLI`);
    if (csv !== want.csv) failures.push(`example ${i}: CSV differs from the CLI`);
    if (shots) await page.screenshot({ path: `${shots}/example-${i}.png`, fullPage: true });
    await page.locator('#back').click();
  }
  await withCamelot(page);
  await longPdf(page);
  await secondVisit(context);
  const shared = examples.at(-1); // a shared link opens its example in a fresh tab
  const tab = await browser.newPage();
  await tab.goto(`${url}#${shared.id}`);
  await tab.waitForSelector(`#doc-title >> text=${shared.title}`, { timeout: 60_000 }).catch(() => failures.push(`link #${shared.id} did not open its example`));
  console.log(`link #${shared.id}: ${await tab.locator('#doc-title').innerText()}`);
  await tab.close();
  if (shots) {
    await page.emulateMedia({ colorScheme: 'dark' });
    await page.screenshot({ path: `${shots}/home-dark.png`, fullPage: true });
  }
} catch (e) {
  failures.push(e.message);
} finally {
  await browser.close();
}
for (const f of failures) console.log('FAIL', f);
process.exit(failures.length ? 1 : 0);
