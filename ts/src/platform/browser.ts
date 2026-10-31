/**
 * A browser (or any runtime without Node's modules): downloads through
 * `fetch`, decompression through `DecompressionStream`. No file system,
 * no `git`; private addresses are the browser's business.
 *
 * @internal
 */

import { type Download, DownloadError, type DownloadOptions, type Platform } from "./types.ts";

async function decompress(data: Uint8Array, format: "deflate-raw" | "gzip", max: number): Promise<Uint8Array> {
  const reader = new Blob([data as BlobPart]).stream().pipeThrough(new DecompressionStream(format)).getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    total += value.length;
    if (total > max) {
      await reader.cancel();
      throw new RangeError("output too large");
    }
    chunks.push(value);
  }
  const out = new Uint8Array(total);
  let at = 0;
  for (const c of chunks) {
    out.set(c, at);
    at += c.length;
  }
  return out;
}

async function download(address: string, options: DownloadOptions): Promise<Download> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), options.timeoutMs);
  const signal = options.signal ? AbortSignal.any([options.signal, controller.signal]) : controller.signal;
  try {
    const res = await fetch(address, { redirect: "follow", signal });
    if (!res.ok) throw new DownloadError(`HTTP Error ${res.status}: ${res.url || address}`);
    const headers: Record<string, string> = {};
    res.headers.forEach((v, k) => (headers[k.toLowerCase()] = v));
    const tooBig = `Remote file exceeds max size (${Math.floor(options.maxBytes / (1024 * 1024))} MB): ${address}`;
    const declared = headers["content-length"];
    if (declared && /^\d+$/u.test(declared) && Number(declared) > options.maxBytes) throw new DownloadError(tooBig);
    const reader = res.body?.getReader();
    const chunks: Uint8Array[] = [];
    let total = 0;
    while (reader) {
      const { done, value } = await reader.read();
      if (done) break;
      total += value.length;
      if (total > options.maxBytes) {
        await reader.cancel();
        throw new DownloadError(tooBig);
      }
      chunks.push(value);
    }
    const body = new Uint8Array(total);
    let at = 0;
    for (const c of chunks) {
      body.set(c, at);
      at += c.length;
    }
    return { url: res.url || address, status: res.status, headers, body };
  } finally {
    clearTimeout(timer);
  }
}

export const platform: Platform = {
  name: "browser",
  fs: null,
  env: () => undefined,
  inflateRaw: (data, max) => decompress(data, "deflate-raw", max),
  gunzip: (data, max) => decompress(data, "gzip", max),
  download,
  gitClone: null,
  emitWarning: (message, type) => console.warn(`${type}: ${message}`),
};
