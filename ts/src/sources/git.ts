/**
 * Repository facts for overviews: branch, commit, origin. Read from the
 * `.git` folder, never by running `git` (a repository's configuration can
 * make git commands run programs).
 *
 * @internal
 */

import type { FileSystem } from "../platform/types.ts";

export interface GitInfo {
  branch: string | null;
  commit: string | null;
  remote: string | null;
}

/** `main @ 1a2b3c4d (https://github.com/o/r)`. */
export function gitSummary(info: GitInfo): string {
  let head = info.branch ?? "detached";
  head += info.commit ? ` @ ${info.commit.slice(0, 8)}` : " (no commits yet)";
  return info.remote ? `${head} (${info.remote})` : head;
}

/** The nearest folder at or above `start` that holds a `.git`. */
export async function findRepoRoot(fs: FileSystem, start: string): Promise<string | null> {
  let folder = start;
  for (;;) {
    if ((await fs.stat(fs.join(folder, ".git"))) !== null) return folder;
    const parent = fs.dirname(folder);
    if (parent === folder) return null;
    folder = parent;
  }
}

async function read(fs: FileSystem, path: string): Promise<string | null> {
  try {
    return new TextDecoder("utf-8", { ignoreBOM: true }).decode(await fs.readFile(path));
  } catch {
    return null;
  }
}

const HASH = /^[0-9a-f]{40,64}$/u;

async function gitDir(fs: FileSystem, root: string): Promise<string | null> {
  const dotGit = fs.join(root, ".git");
  const info = await fs.stat(dotGit);
  if (info?.isDir) return dotGit;
  const text = (await read(fs, dotGit))?.trim();
  if (text?.startsWith("gitdir:")) {
    const target = text.slice("gitdir:".length).trim();
    return fs.isAbsolute(target) ? target : fs.absolute(fs.join(root, target));
  }
  return null;
}

async function resolveRef(fs: FileSystem, dir: string, common: string, ref: string): Promise<string | null> {
  for (const base of [dir, common]) {
    const text = (await read(fs, fs.join(base, ...ref.split("/"))))?.trim();
    if (text && HASH.test(text)) return text;
  }
  for (const line of ((await read(fs, fs.join(common, "packed-refs"))) ?? "").split(/\r?\n/u)) {
    const parts = line.trim().split(/\s+/u);
    if (parts.length === 2 && parts[1] === ref) return parts[0]!;
  }
  return null;
}

/** `user:token@` removed from a URL. */
export function stripCredentials(url: string): string {
  const m = /^([a-zA-Z][a-zA-Z0-9+.-]*):\/\/([^/?#]*)(.*)$/su.exec(url);
  if (!m || !m[2]!.includes("@")) return url;
  // As Python's urlsplit: the host name lowercased, a port kept.
  const hostport = m[2]!.slice(m[2]!.lastIndexOf("@") + 1);
  const colon = hostport.lastIndexOf(":");
  const host = colon > hostport.lastIndexOf("]") ? `${hostport.slice(0, colon).toLowerCase()}${hostport.slice(colon)}` : hostport.toLowerCase();
  return `${m[1]}://${host}${m[3]}`;
}

function originUrl(config: string): string | null {
  let section: string | null = null;
  for (const raw of config.split(/\r?\n/u)) {
    const line = raw.trim();
    if (line.startsWith("[")) {
      section = line;
      continue;
    }
    if (section && /^\[remote\s+"origin"\]$/u.test(section)) {
      const eq = line.indexOf("=");
      const key = eq === -1 ? line : line.slice(0, eq);
      const value = eq === -1 ? "" : line.slice(eq + 1).trim();
      if (key.trim().toLowerCase() === "url" && value) return stripCredentials(value);
    }
  }
  return null;
}

export async function readGitInfo(fs: FileSystem, root: string): Promise<GitInfo | null> {
  const dir = await gitDir(fs, root);
  if (dir === null) return null;
  const commonText = await read(fs, fs.join(dir, "commondir"));
  const common = commonText ? fs.absolute(fs.join(dir, commonText.trim())) : dir;
  const head = ((await read(fs, fs.join(dir, "HEAD"))) ?? "").trim();
  let branch: string | null = null;
  let commit: string | null = null;
  if (head.startsWith("ref:")) {
    const ref = head.slice(4).trim();
    branch = ref.startsWith("refs/heads/") ? ref.slice("refs/heads/".length) : ref;
    commit = await resolveRef(fs, dir, common, ref);
  } else if (HASH.test(head)) commit = head;
  const remote = originUrl((await read(fs, fs.join(common, "config"))) ?? "");
  return { branch, commit, remote };
}
