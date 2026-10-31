/**
 * An input into files and tree reports (contract/reading.md, "Sources").
 *
 * @internal
 */

import { platform } from "#platform";
import type { FileSystem } from "../platform/types.ts";
import { isArchiveName } from "./archives.ts";
import { downloadFile } from "./download.ts";
import {
  looksLikeGlob,
  MAX_SCAN_ENTRIES_DEFAULT,
  readArchive,
  readFolder,
  readPattern,
  type SourceFile,
  type TreeOptions,
  type TreeReport,
} from "./tree.ts";

/** A source of your own: the files at an address it was registered for. */
export interface SourceSpec {
  /** Inputs starting with one of these are this source's (`s3://`). */
  prefixes: readonly string[];
  /** The files: `File`s (named bytes), in order. */
  unpack(input: string, context: { signal?: AbortSignal | undefined }): Iterable<File> | Promise<Iterable<File>>;
}

/** Registered sources, by prefix, in registration order. */
export const sources = new Map<string, SourceSpec>();

export interface Resolution {
  files: SourceFile[];
  reports: TreeReport[];
}

export interface ResolveSettings {
  blockPrivateUrls: boolean;
  maxDownload: number;
  signal?: AbortSignal | undefined;
}

/** An input that is not a file, folder, pattern or address. */
export class UnpackError extends Error {
  override name = "UnpackError";
}

const OWNER_REPO = /^[a-zA-Z0-9][-a-zA-Z0-9_.]*[a-zA-Z0-9]?\/[a-zA-Z0-9][-a-zA-Z0-9_.]*[a-zA-Z0-9]?(\.git)?$/u;

export function isGithubRepoRoot(url: string): boolean {
  if (!url.startsWith("https://github.com/")) return false;
  try {
    return new URL(url).pathname.split("/").filter(Boolean).length === 2;
  } catch {
    return false;
  }
}

function query(text: string): URLSearchParams {
  return new URLSearchParams(text); // as Python's parse_qsl: "+" is a space, %XX decoded
}

/** `[clone address, ref]` of a GitHub input; throws for an unsafe one. */
export function githubCloneSpec(spec: string): [string, string | null] {
  let ownerRepo: string;
  let ref: string | null;
  if (spec.startsWith("github://")) {
    const rest = spec.slice("github://".length);
    const q = rest.indexOf("?");
    ownerRepo = (q === -1 ? rest : rest.slice(0, q)).replace(/^\/+|\/+$/gu, "");
    ref = q === -1 ? null : query(rest.slice(q + 1)).get("ref");
  } else {
    const u = new URL(spec);
    const parts = u.pathname.split("/").filter(Boolean);
    if (parts.length !== 2) throw new UnpackError("Unsupported GitHub spec");
    ownerRepo = parts.join("/");
    ref = query(u.search.slice(1)).get("ref");
  }
  if (!OWNER_REPO.test(ownerRepo) || ["--", "..", ";", "|", "&", "$", "`", "\n", "\r"].some((p) => ownerRepo.includes(p))) {
    throw new UnpackError(`Invalid GitHub owner/repo format: ${ownerRepo}`);
  }
  const url = `https://github.com/${ownerRepo.endsWith(".git") ? ownerRepo : `${ownerRepo}.git`}`;
  return [url, ref || null];
}

/** `owner/repo` (plus `@ref`) for a repository's overview. */
export function githubDisplayName(spec: string): string {
  let path: string;
  let q: string;
  if (spec.startsWith("github://")) {
    const rest = spec.slice("github://".length);
    const at = rest.indexOf("?");
    path = at === -1 ? rest : rest.slice(0, at);
    q = at === -1 ? "" : rest.slice(at + 1);
  } else {
    const u = new URL(spec);
    path = u.pathname;
    q = u.search.slice(1);
  }
  const name = path.replace(/^\/+|\/+$/gu, "").replace(/\.git$/u, "");
  const ref = query(q).get("ref");
  return ref ? `${name}@${ref}` : name;
}

function maxScan(): number {
  const v = platform.env("ATT_MAX_SCAN_ENTRIES");
  return v !== undefined && /^\d+$/u.test(v.trim()) ? Number(v.trim()) : MAX_SCAN_ENTRIES_DEFAULT;
}

function needFs(input: string): FileSystem {
  if (platform.fs === null) {
    throw new UnpackError(`${input}: paths, folders and patterns are read in Node, Deno or Bun; in a browser, give a URL or a File`);
  }
  return platform.fs;
}

function localPath(fs: FileSystem, input: string): string {
  if (input.startsWith("file://")) {
    const host = /^file:\/\/([^/]*)/u.exec(input)![1]!;
    if (host !== "" && host !== "localhost") throw new UnpackError(`file:// URIs must name a local file (no host), got '${input}'`);
    return fs.fromFileUrl(input.replace(/^file:\/\/localhost/u, "file://"));
  }
  if (input === "~" || input.startsWith("~/")) return fs.join(fs.home(), input.slice(2));
  return input;
}

const withWarnings = (report: TreeReport, warnings: readonly string[]): TreeReport => {
  report.warnings.push(...warnings);
  return report;
};

/** The files and reports of one input (its options already taken out). */
export async function resolve(input: string, opts: TreeOptions, optionWarnings: readonly string[], settings: ResolveSettings): Promise<Resolution> {
  const done = (files: SourceFile[], report?: TreeReport): Resolution => ({
    files,
    reports: report ? [withWarnings(report, optionWarnings)] : [],
  });
  for (const [prefix, spec] of sources) {
    if (input.startsWith(prefix)) {
      const files: SourceFile[] = [];
      for (const f of await spec.unpack(input, { signal: settings.signal })) {
        files.push({ name: f.name, data: new Uint8Array(await f.arrayBuffer()) });
      }
      return done(files);
    }
  }
  if (input.startsWith("github://") || isGithubRepoRoot(input)) {
    const fs = needFs(input);
    if (platform.gitClone === null) throw new UnpackError("cloning a repository needs git, which this platform cannot run");
    const [url, ref] = githubCloneSpec(input);
    const dir = await fs.makeTempDir("attachments_github_");
    try {
      await platform.gitClone(url, ref, dir);
      const [files, report] = await readFolder(fs, dir, opts, input, maxScan(), "repo", githubDisplayName(input));
      return done(files, report);
    } finally {
      await fs.remove(dir);
    }
  }
  if (input.startsWith("http://") || input.startsWith("https://")) {
    const file = await downloadFile(input, { blockPrivate: settings.blockPrivateUrls, maxBytes: settings.maxDownload, signal: settings.signal });
    if (isArchiveName(file.name)) {
      const [files, report] = await readArchive(file.name, file.data, opts, input);
      return done(files, report);
    }
    return done([file]);
  }
  const fs = needFs(input);
  const local = localPath(fs, input);
  const info = await fs.stat(local);
  if (info?.isDir) {
    const [files, report] = await readFolder(fs, local, opts, input, maxScan());
    return done(files, report);
  }
  if (info?.isFile) {
    const data = await fs.readFile(local);
    const name = fs.basename(local);
    if (isArchiveName(name)) {
      const [files, report] = await readArchive(name, data, opts, input);
      return done(files, report);
    }
    return done([{ name, data }]);
  }
  if (looksLikeGlob(local)) {
    const [files, report] = await readPattern(fs, local, opts, maxScan());
    return done(files, report);
  }
  throw new UnpackError(`Unsupported or non-existent input: ${input}`);
}

/** Named bytes, read as a local file of that name would be. */
export async function resolveBytes(name: string, data: Uint8Array, opts: TreeOptions, optionWarnings: readonly string[]): Promise<Resolution> {
  if (isArchiveName(name)) {
    const [files, report] = await readArchive(name, data, opts, name);
    return { files, reports: [withWarnings(report, optionWarnings)] };
  }
  return { files: [{ name, data }], reports: [] };
}
