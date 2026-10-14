export async function get(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url}: HTTP ${r.status}`);
  return r;
}

export const bytes = async (url) => new Uint8Array(await (await get(url)).arrayBuffer());

const store = () => caches.open('pdfexorcist-files').catch(() => null); // some private windows have no Cache Storage

/** Gets files.json from build.py as [path, url?v=hash] pairs. The browser gets it from the server each time, so a new deploy shows immediately. */
export const manifest = async () => (await fetch('files.json', { cache: 'no-cache' })).json();

/** Returns the bytes of a content-versioned url. After the first visit, the bytes come from Cache Storage. */
export async function kept(url) {
  const cache = await store();
  const hit = await cache?.match(url).catch(() => null);
  if (hit) return new Uint8Array(await hit.arrayBuffer());
  const data = await bytes(url);
  await cache?.put(url, new Response(data)).catch(() => {}); // if the cache is full, the next visit downloads the file again
  return data;
}

/** Returns true when Cache Storage has all the urls. */
export async function allKept(urls) {
  const cache = await store();
  if (!cache) return false;
  const hits = await Promise.all(urls.map((u) => cache.match(u).catch(() => null)));
  return hits.every(Boolean);
}

/** Removes the files in Cache Storage that are not in urls. */
export async function prune(urls) {
  const cache = await store();
  if (!cache) return;
  const live = new Set(urls.map((u) => new URL(u, location.href).href));
  await Promise.all((await cache.keys()).filter((r) => !live.has(r.url)).map((r) => cache.delete(r)));
}

/** Gets a wasm file with kept() and compiles it. */
export const keptWasm = async (url) => WebAssembly.compile(await kept(url));
