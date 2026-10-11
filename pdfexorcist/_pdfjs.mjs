// One JSON line per page: [[x0, x1, top, bottom, text], ...] in points, y down.
// usage: node _pdfjs.mjs <pdfjs-dist dir> <pdf>; the browser build imports pdfjsLines

/** pdfjs: the pdfjs-dist module; data: the PDF's bytes; write(line) gets each page as it is read */
export async function pdfjsLines(pdfjs, data, write) {
  const task = pdfjs.getDocument({ data, verbosity: 0 });
  const doc = await task.promise;
  for (let i = 1; i <= doc.numPages; i++) {
    const page = await doc.getPage(i);
    const view = page.getViewport({ scale: 1 });
    const words = [];
    for (const it of (await page.getTextContent()).items) {
      if (!it.str?.trim()) continue;
      const [x0, y] = view.convertToViewportPoint(it.transform[4], it.transform[5]); // baseline
      const last = words.at(-1);
      if (last && last[3] === y && Math.abs(x0 - last[1]) < 0.5) {
        // pdf.js splits a word into touching runs ("4", "7", ". Average")
        last[1] = x0 + it.width;
        last[4] += it.str;
      } else words.push([x0, x0 + it.width, y - it.height, y, it.str]);
    }
    write(JSON.stringify(words) + '\n');
    page.cleanup();
  }
  await task.destroy();
}

if (globalThis.process?.argv[1]?.endsWith('_pdfjs.mjs')) {
  const { readFileSync } = await import('node:fs');
  const { join } = await import('node:path');
  const { pathToFileURL } = await import('node:url');
  const [dist, file] = process.argv.slice(2);
  const pdfjs = await import(pathToFileURL(join(dist, 'legacy/build/pdf.mjs')).href);
  await pdfjsLines(pdfjs, new Uint8Array(readFileSync(file)), (line) => process.stdout.write(line));
}
