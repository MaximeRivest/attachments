/**
 * Node (and Deno, Bun): files, `git`, and an HTTP client that checks
 * every address it connects to when private addresses are blocked (the
 * check happens at connection time, so a name cannot resolve to a
 * public address when checked and a private one when used).
 *
 * @internal
 */

import buffer from "node:buffer";
import { spawn } from "node:child_process";
import { lookup as dnsLookup, type LookupAddress } from "node:dns";
import { promises as fs } from "node:fs";
import http from "node:http";
import https from "node:https";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";
import zlib from "node:zlib";

import { isAddress, isGlobal } from "./addresses.ts";
import { type Download, DownloadError, type DownloadOptions, type FileSystem, type Platform } from "./types.ts";

/** Python's `os.path.realpath` (not strict): what exists is resolved, the rest kept. */
async function realpathLoose(p: string, hops = 0): Promise<string> {
  const absolute = path.resolve(p);
  try {
    return await fs.realpath(absolute);
  } catch {
    if (hops > 40) return absolute;
    try {
      const target = await fs.readlink(absolute);
      return realpathLoose(path.resolve(path.dirname(absolute), target), hops + 1);
    } catch {
      const parent = path.dirname(absolute);
      if (parent === absolute) return absolute;
      return path.join(await realpathLoose(parent, hops + 1), path.basename(absolute));
    }
  }
}

const fileSystem: FileSystem = {
  cwd: () => process.cwd(),
  home: () => os.homedir(),
  absolute: (p) => path.resolve(p),
  realpath: (p) => fs.realpath(p),
  realpathLoose,
  async stat(p) {
    try {
      const s = await fs.stat(p);
      return { isFile: s.isFile(), isDir: s.isDirectory(), size: s.size };
    } catch {
      return null;
    }
  },
  async readdir(p) {
    const entries = await fs.readdir(p, { withFileTypes: true });
    return entries.map((e) => ({ name: e.name, isSymlink: e.isSymbolicLink(), isDir: e.isDirectory() }));
  },
  async readFile(p) {
    const b = await fs.readFile(p);
    return new Uint8Array(b.buffer, b.byteOffset, b.byteLength);
  },
  async readHead(p, max) {
    const handle = await fs.open(p, "r");
    try {
      const buf = new Uint8Array(max);
      const { bytesRead } = await handle.read(buf, 0, max, 0);
      return buf.subarray(0, bytesRead);
    } finally {
      await handle.close();
    }
  },
  join: (...parts) => path.join(...parts),
  dirname: (p) => path.dirname(p),
  basename: (p) => path.basename(p),
  inside(p, from) {
    const rel = path.relative(from, p);
    if (rel === "") return "";
    if (rel.startsWith("..") || path.isAbsolute(rel)) return null;
    return rel.split(path.sep).join("/");
  },
  isAbsolute: (p) => path.isAbsolute(p),
  fromFileUrl: (u) => fileURLToPath(u),
  makeTempDir: (prefix) => fs.mkdtemp(path.join(os.tmpdir(), prefix)),
  remove: (p) => fs.rm(p, { recursive: true, force: true }),
};

type LookupCallback = (err: NodeJS.ErrnoException | null, address: string | LookupAddress[], family?: number) => void;

/** A `lookup` for sockets that refuses non-public addresses. */
function guardedLookup(hostname: string, options: { all?: boolean; family?: number }, callback: LookupCallback): void {
  dnsLookup(hostname, { ...options, all: true }, (err, addresses) => {
    if (err) return callback(err, []);
    const list = addresses as LookupAddress[];
    const bad = list.find((a) => !isGlobal(a.address));
    if (bad) {
      return callback(
        new DownloadError(`Blocked: host '${hostname}' resolves to non-public address ${bad.address}`) as NodeJS.ErrnoException,
        [],
      );
    }
    if (options.all) callback(null, list);
    else callback(null, list[0]!.address, list[0]!.family);
  });
}

const REDIRECTS = new Set([301, 302, 303, 307, 308]);
const MAX_REDIRECTS = 10;

function requestOnce(url: URL, options: DownloadOptions): Promise<{ status: number; headers: Record<string, string>; body: Uint8Array; location?: string }> {
  return new Promise((resolve, reject) => {
    const client = url.protocol === "https:" ? https : http;
    const host = url.hostname.replace(/^\[|\]$/gu, "");
    if (options.blockPrivate && isAddress(host) && !isGlobal(host)) {
      reject(new DownloadError(`Blocked URL ${url.href}: host '${host}' is a non-public address`));
      return;
    }
    const req = client.request(
      url,
      {
        method: "GET",
        headers: { "User-Agent": options.userAgent, "Accept-Encoding": "identity" },
        ...(options.blockPrivate ? { lookup: guardedLookup as never } : {}),
        signal: options.signal,
      },
      (res) => {
        const headers: Record<string, string> = {};
        for (const [k, v] of Object.entries(res.headers)) {
          if (v !== undefined) headers[k.toLowerCase()] = Array.isArray(v) ? v.join(", ") : v;
        }
        const status = res.statusCode ?? 0;
        if (REDIRECTS.has(status) && headers["location"]) {
          res.resume();
          resolve({ status, headers, body: new Uint8Array(), location: headers["location"] });
          return;
        }
        const declared = headers["content-length"];
        const tooBig = `Remote file exceeds max size (${Math.floor(options.maxBytes / (1024 * 1024))} MB): ${url.href}`;
        if (declared && /^\d+$/u.test(declared) && Number(declared) > options.maxBytes) {
          res.destroy();
          reject(new DownloadError(tooBig));
          return;
        }
        const chunks: Buffer[] = [];
        let total = 0;
        res.on("data", (chunk: Buffer) => {
          total += chunk.length;
          if (total > options.maxBytes) {
            res.destroy();
            reject(new DownloadError(tooBig));
            return;
          }
          chunks.push(chunk);
        });
        res.on("end", () => {
          const b = Buffer.concat(chunks);
          resolve({ status, headers, body: new Uint8Array(b.buffer, b.byteOffset, b.byteLength) });
        });
        res.on("error", reject);
      },
    );
    req.setTimeout(options.timeoutMs, () => req.destroy(new DownloadError(`timed out after ${options.timeoutMs / 1000} s`)));
    req.on("error", reject);
    req.end();
  });
}

async function download(address: string, options: DownloadOptions): Promise<Download> {
  let url = new URL(address);
  for (let hop = 0; ; hop++) {
    if (url.protocol !== "http:" && url.protocol !== "https:") {
      throw new DownloadError(`Blocked URL scheme '${url.protocol.slice(0, -1)}' (only http/https allowed)`);
    }
    const answer = await requestOnce(url, options);
    if (answer.location !== undefined) {
      if (hop >= MAX_REDIRECTS) throw new DownloadError(`more than ${MAX_REDIRECTS} redirects from ${address}`);
      url = new URL(answer.location, url);
      continue;
    }
    if (answer.status < 200 || answer.status >= 300) {
      throw new DownloadError(`HTTP Error ${answer.status}: ${url.href}`);
    }
    return { url: url.href, status: answer.status, headers: answer.headers, body: answer.body };
  }
}

function gitClone(url: string, ref: string | null, dest: string): Promise<void> {
  const args = ["clone", "--depth", "1", ...(ref ? ["--branch", ref] : []), url, dest];
  return new Promise((resolve, reject) => {
    const child = spawn("git", args, { stdio: ["ignore", "ignore", "pipe"], env: { ...process.env, GIT_TERMINAL_PROMPT: "0" } });
    let stderr = "";
    child.stderr.on("data", (d: Buffer) => (stderr += d.toString()));
    child.on("error", (e) => reject(new Error(`git clone failed: ${e.message}`)));
    child.on("close", (code) => (code === 0 ? resolve() : reject(new Error(`git clone failed: ${stderr.trim() || `exit ${code}`}`))));
  });
}

const inflateRawAsync = promisify(zlib.inflateRaw) as (b: Uint8Array, o: zlib.ZlibOptions) => Promise<Buffer>;
const gunzipAsync = promisify(zlib.gunzip) as (b: Uint8Array, o: zlib.ZlibOptions) => Promise<Buffer>;

async function capped(run: () => Promise<Buffer>): Promise<Uint8Array> {
  try {
    return asBytes(await run());
  } catch (err) {
    if ((err as { code?: string }).code === "ERR_BUFFER_TOO_LARGE") throw new RangeError("output too large");
    throw err;
  }
}

const cap = (max: number): number => Math.min(max, buffer.constants.MAX_LENGTH);

const asBytes = (b: Buffer): Uint8Array => new Uint8Array(b.buffer, b.byteOffset, b.byteLength);

export const platform: Platform = {
  name: "node",
  fs: fileSystem,
  env: (name) => process.env[name],
  inflateRaw: (data, max) => capped(() => inflateRawAsync(data, { maxOutputLength: cap(max) })),
  gunzip: (data, max) => capped(() => gunzipAsync(data, { maxOutputLength: cap(max) })),
  download,
  gitClone,
  emitWarning: (message, type) => process.emitWarning(message, { type }),
};
