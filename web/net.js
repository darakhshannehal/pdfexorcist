export async function get(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url}: HTTP ${r.status}`);
  return r;
}

/** Returns the bytes at url; got(n) is called per chunk. */
export async function bytes(url, got) {
  const r = await get(url);
  if (!got || !r.body) return new Uint8Array(await r.arrayBuffer());
  const reader = r.body.getReader();
  const parts = [];
  let size = 0;
  for (let c; !(c = await reader.read()).done; ) {
    parts.push(c.value);
    size += c.value.length;
    got(c.value.length);
  }
  const out = new Uint8Array(size);
  parts.reduce((at, c) => (out.set(c, at), at + c.length), 0);
  return out;
}

const store = () => caches.open('pdfexorcist-files').catch(() => null); // some private windows have no Cache Storage

/** Gets files.json from build.py as [path, url?v=hash] pairs. The browser gets it from the server each time, so a new deploy shows immediately. */
export const manifest = async () => (await fetch('files.json', { cache: 'no-cache' })).json();

/** Returns the bytes of a content-versioned url. After the first visit, the bytes come from Cache Storage. */
export async function kept(url, got) {
  const cache = await store();
  const hit = await cache?.match(url).catch(() => null);
  if (hit) return new Uint8Array(await hit.arrayBuffer());
  const data = await bytes(url, got);
  await cache?.put(url, new Response(data)).catch(() => {}); // if the cache is full, the next visit downloads the file again
  return data;
}

/** Returns the urls that Cache Storage does not have. */
export async function missing(urls) {
  const cache = await store();
  if (!cache) return urls;
  const hits = await Promise.all(urls.map((u) => cache.match(u).catch(() => null)));
  return urls.filter((_, i) => !hits[i]);
}

/** Removes the files in Cache Storage that are not in urls. */
export async function prune(urls) {
  const cache = await store();
  if (!cache) return;
  const live = new Set(urls.map((u) => new URL(u, location.href).href));
  await Promise.all((await cache.keys()).filter((r) => !live.has(r.url)).map((r) => cache.delete(r)));
}

/** Gets a wasm file with kept() and compiles it. */
export const keptWasm = async (url, got) => WebAssembly.compile(await kept(url, got));
