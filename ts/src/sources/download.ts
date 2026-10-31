/**
 * Web addresses (contract/reading.md, "Downloads"): one GET, the file's
 * name from Content-Disposition or the address, made to agree with the
 * declared Content-Type.
 *
 * @internal
 */

import { READING } from "../generated/reading.ts";
import { platform } from "#platform";
import { sanitizeMemberName } from "./archives.ts";
import type { SourceFile } from "./tree.ts";

const TYPE_EXTENSIONS: Record<string, readonly [string, readonly string[]]> = READING.type_extensions as unknown as Record<
  string,
  readonly [string, readonly string[]]
>;
const DYNAMIC = new Set<string>(READING.dynamic_page_extensions);
const REAL_EXTENSION = /\.[a-z][a-z0-9]{0,6}$/iu;

export const USER_AGENT = "attachments-unpack/1.0 (+https://github.com/MaximeRivest/att)";
export const MAX_DOWNLOAD_BYTES = 256 * 1024 * 1024;

/** Python's `urllib.parse.unquote` (UTF-8, invalid sequences replaced). */
export function unquote(text: string): string {
  if (!text.includes("%")) return text;
  const bytes: number[] = [];
  let out = "";
  const flush = (): void => {
    if (bytes.length) {
      out += new TextDecoder("utf-8", { ignoreBOM: true }).decode(new Uint8Array(bytes));
      bytes.length = 0;
    }
  };
  for (let i = 0; i < text.length; i++) {
    if (text[i] === "%" && /^[0-9a-fA-F]{2}$/u.test(text.slice(i + 1, i + 3))) {
      bytes.push(parseInt(text.slice(i + 1, i + 3), 16));
      i += 2;
    } else {
      flush();
      out += text[i];
    }
  }
  flush();
  return out;
}

const strip = (s: string): string => s.trim().replace(/^["']+|["']+$/gu, "");

/** The file name a `Content-Disposition` header gives, if any. */
export function filenameFromContentDisposition(cd: string | null | undefined): string | null {
  if (!cd) return null;
  let m = /filename\*\s*=\s*([^;]+)/iu.exec(cd);
  if (m) {
    let value = strip(m[1]!);
    const at = value.indexOf("''");
    if (at !== -1) value = value.slice(at + 2);
    return unquote(value);
  }
  m = /filename\s*=\s*([^;]+)/iu.exec(cd);
  return m ? strip(m[1]!) : null;
}

/** The `raw.githubusercontent.com` address of a github.com file page. */
export function githubRawUrl(url: string): string | null {
  let parsed: URL;
  try {
    parsed = new URL(url);
  } catch {
    return null;
  }
  if (parsed.hostname !== "github.com" && parsed.hostname !== "www.github.com") return null;
  const parts = parsed.pathname.split("/").filter(Boolean);
  if (parts.length >= 5 && parts[2] === "blob") {
    const [owner, repo, , ref, ...rest] = parts;
    return `https://raw.githubusercontent.com/${owner}/${repo}/${ref}/${rest.join("/")}`;
  }
  return null;
}

/** `[name, warning]`: the name made to agree with the declared type. */
export function nameForContentType(name: string, contentType: string | null | undefined, url: string): [string, string | null] {
  const mime = (contentType ?? "").split(";")[0]!.trim().toLowerCase();
  const entry = TYPE_EXTENSIONS[mime];
  if (entry === undefined) return [name, null];
  const [extension, agreeing] = entry;
  if (agreeing.some((a) => name.toLowerCase().endsWith(a))) return [name, null];
  const old = REAL_EXTENSION.exec(name);
  const renamed = name + extension;
  if (old === null || DYNAMIC.has(old[0].toLowerCase())) return [renamed, null];
  const kind = extension === ".html" ? "a web page" : `${extension.slice(1).toUpperCase()} data`;
  let warning = `The server sent ${kind} (${mime}), not the ${old[0]} file its address suggests; it was read as ${extension.slice(1).toUpperCase()}.`;
  const raw = githubRawUrl(url);
  if (raw) warning += ` For the file itself, use ${raw}`;
  return [renamed, warning];
}

function lastSegment(url: string): string {
  try {
    const path = new URL(url).pathname;
    return path.slice(path.lastIndexOf("/") + 1);
  } catch {
    return "";
  }
}

export interface DownloadSettings {
  blockPrivate: boolean;
  maxBytes: number;
  signal?: AbortSignal | undefined;
}

/** Download one address as a named file with its final address. */
export async function downloadFile(url: string, settings: DownloadSettings): Promise<SourceFile> {
  const env = (k: string): string | undefined => platform.env(k);
  const maxEnv = env("ATT_MAX_DOWNLOAD_BYTES");
  const ceiling = maxEnv !== undefined && /^\d+$/u.test(maxEnv) ? Number(maxEnv) : MAX_DOWNLOAD_BYTES;
  const answer = await platform.download(url, {
    userAgent: env("ATT_USER_AGENT") ?? USER_AGENT,
    maxBytes: Math.min(settings.maxBytes, ceiling),
    timeoutMs: 60_000,
    blockPrivate: settings.blockPrivate,
    signal: settings.signal,
  });
  const contentType = answer.headers["content-type"] ?? null;
  let filename = filenameFromContentDisposition(answer.headers["content-disposition"]);
  if (!filename) {
    filename = unquote(lastSegment(answer.url));
    if (!filename) {
      const known = (contentType ?? "").split(";")[0]!.trim().toLowerCase();
      filename = known in TYPE_EXTENSIONS ? "index" : "download";
    }
  }
  filename = sanitizeMemberName(filename) || "download";
  const [name, warning] = nameForContentType(filename, contentType, answer.url);
  return { name, data: answer.body, url: answer.url, ...(warning ? { warnings: [warning] } : {}) };
}
