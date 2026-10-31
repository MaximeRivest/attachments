/**
 * Trees of files: folders, wildcard patterns, archives, cloned
 * repositories (contract/reading.md, "Trees"). Listed first (sorted, with
 * the skip rules), then read within the limits, with a report of what
 * was left out and why.
 *
 * @internal
 */

import type { OptionValue } from "../options.ts";
import type { FileSystem } from "../platform/types.ts";
import { comparePoints } from "../text.ts";
import { explodeArchive, isArchiveName } from "./archives.ts";
import { findRepoRoot, type GitInfo, readGitInfo } from "./git.ts";
import {
  CACHEDIR_SIGNATURE,
  compileRules,
  decide,
  IGNORE_FILES,
  IgnoreEngine,
  type Rule,
  splitLines,
  splitPatterns,
} from "./ignore.ts";

export const DEFAULT_MAX_FILES = 1000;
export const DEFAULT_MAX_SIZE = 256 * 1024 * 1024;
const MAX_IGNORE_FILE = 1024 * 1024;
const EXAMPLES = 5;

export const SYMLINK = "link outside the folder";
export const SPECIAL = "not a regular file";
export const UNREADABLE = "unreadable";
export const NOT_RECURSIVE = "subfolder (recursive: false)";
export const GLOB_OPTION = "not matching glob";

/** A folder option with a value that cannot be used. */
export class InvalidSourceOption extends RangeError {
  override name = "InvalidSourceOption";
}

/** A file of a tree: its name (path from the tree's root) and bytes. */
export interface SourceFile {
  name: string;
  data: Uint8Array;
  /** The address it was downloaded from (after redirects). */
  url?: string;
  /** For the artifact's `meta.warnings`. */
  warnings?: readonly string[];
}

const SIZE = /^\s*(\d+(?:\.\d+)?)\s*([kmgt]?i?b?)?\s*$/iu;
const SIZE_HELP = "max_size must be a size like 50MB, 1.5GiB or a number of bytes (0 = no limit)";

function pyRepr(value: unknown): string {
  if (typeof value === "string") return `'${value}'`;
  if (typeof value === "boolean") return value ? "True" : "False";
  return String(value);
}

/** Bytes from a number or text like `50MB`, `1.5 GiB`, `500k`. */
export function parseSize(value: unknown): number {
  if (typeof value === "boolean") throw new InvalidSourceOption(`${SIZE_HELP}, got ${pyRepr(value)}`);
  if (typeof value === "number" && Number.isInteger(value)) {
    if (value < 0) throw new InvalidSourceOption(`${SIZE_HELP}, got ${value}`);
    return value;
  }
  const match = SIZE.exec(String(value));
  if (!match) throw new InvalidSourceOption(`${SIZE_HELP}, got ${pyRepr(value)}`);
  const number = Number(match[1]);
  const unit = (match[2] ?? "").toLowerCase();
  const base = unit.includes("i") ? 1024 : 1000;
  const power = { "": 0, k: 1, m: 2, g: 3, t: 4 }[/^[kmgt]/u.test(unit) ? unit[0]! : ""] as number;
  return Math.trunc(number * base ** power);
}

const DEFAULT_WORDS = new Set(["standard", "auto", "default", "gitignore", "attachmentsignore"]);
const NONE_WORDS = new Set(["none", "raw", "all"]);

export interface TreeOptions {
  files: boolean;
  tree: boolean | "auto";
  recursive: boolean;
  hidden: boolean;
  defaults: boolean;
  ignore: string[];
  glob: string[];
  maxFiles: number;
  maxSize: number;
}

/** Folder options from resolved values: `[options, warnings]`. Throws {@link InvalidSourceOption}. */
export function treeOptions(options: Record<string, OptionValue>): [TreeOptions, string[]] {
  const warnings: string[] = [];
  let defaults = true;
  const patterns: string[] = [];
  for (const pattern of splitPatterns(options["ignore"])) {
    const word = pattern.toLowerCase();
    if (NONE_WORDS.has(word)) defaults = false;
    else if (DEFAULT_WORDS.has(word)) continue;
    else if (word === "minimal") warnings.push("ignore: 'minimal' (from attachments 0.25) is not supported; the default rules apply");
    else patterns.push(pattern);
  }
  const maxFiles = options["max_files"] ?? DEFAULT_MAX_FILES;
  if (typeof maxFiles !== "number" || !Number.isInteger(maxFiles) || maxFiles < 0) {
    throw new InvalidSourceOption(`max_files must be an integer >= 0 (0 = no limit), got ${pyRepr(maxFiles)}`);
  }
  const maxSize = parseSize(options["max_size"] ?? DEFAULT_MAX_SIZE);
  let tree = options["tree"] ?? "auto";
  if (typeof tree === "string" && tree.toLowerCase() === "always") tree = true;
  if (tree !== true && tree !== false && String(tree).toLowerCase() !== "auto") {
    throw new InvalidSourceOption(`tree must be true, false or auto, got ${pyRepr(tree)}`);
  }
  return [
    {
      files: options["files"] !== false,
      tree: typeof tree === "boolean" ? tree : "auto",
      recursive: options["recursive"] !== false,
      hidden: options["hidden"] === true,
      defaults,
      ignore: patterns,
      glob: splitPatterns(options["glob"]),
      maxFiles,
      maxSize,
    },
    warnings,
  ];
}

export interface Skipped {
  files: number;
  folders: number;
  examples: string[];
}

export interface Entry {
  path: string;
  size: number;
  /** Archives: members kept. */
  members?: number;
}

export type TreeKind = "folder" | "pattern" | "repo" | "archive";

/** What a tree contained, what was read, what was left out. */
export class TreeReport {
  entries: Entry[] = [];
  skipped = new Map<string, Skipped>();
  limit: "max_files" | "max_size" | null = null;
  notRead = 0;
  scanCapped = false;
  git: GitInfo | null = null;
  warnings: string[] = [];

  readonly label: string;
  readonly kind: TreeKind;
  readonly rootName: string;
  readonly options: TreeOptions;

  constructor(label: string, kind: TreeKind, rootName: string, options: TreeOptions) {
    this.label = label;
    this.kind = kind;
    this.rootName = rootName;
    this.options = options;
  }

  skip(reason: string, path: string, folder = false): void {
    let s = this.skipped.get(reason);
    if (!s) {
      s = { files: 0, folders: 0, examples: [] };
      this.skipped.set(reason, s);
    }
    if (folder) s.folders++;
    else s.files++;
    if (s.examples.length < EXAMPLES) s.examples.push(path + (folder ? "/" : ""));
  }

  get totalBytes(): number {
    return this.entries.reduce((n, e) => n + e.size, 0);
  }

  get filesRead(): number {
    return this.entries.reduce((n, e) => n + (e.members ?? 1), 0);
  }
}

// -- engines -------------------------------------------------------------------

async function readSmall(fs: FileSystem, path: string): Promise<string | null> {
  const s = await fs.stat(path);
  if (!s?.isFile || s.size > MAX_IGNORE_FILE) return null;
  try {
    return decodeReplace(await fs.readFile(path));
  } catch {
    return null;
  }
}

/** UTF-8 with replacement characters; a byte order mark kept. */
export function decodeReplace(data: Uint8Array): string {
  return new TextDecoder("utf-8", { ignoreBOM: true }).decode(data);
}

function startsWith(data: Uint8Array | null, prefix: Uint8Array): boolean {
  if (data === null || data.length < prefix.length) return false;
  for (let i = 0; i < prefix.length; i++) if (data[i] !== prefix[i]) return false;
  return true;
}

async function folderEngine(fs: FileSystem, root: string, opts: TreeOptions, hidden: boolean): Promise<IgnoreEngine> {
  const outer: [string, Rule[]][] = [];
  if (opts.defaults) {
    const repo = await findRepoRoot(fs, root);
    if (repo !== null) {
      let folder = root;
      while (folder !== repo) {
        folder = fs.dirname(folder);
        const prefix = `${fs.inside(root, folder)}/`;
        for (const name of [...IGNORE_FILES].reverse()) {
          const text = await readSmall(fs, fs.join(folder, name));
          if (text) outer.push([prefix, compileRules(splitLines(text))]);
        }
      }
      const prefix = repo === root ? "" : `${fs.inside(root, repo)}/`;
      const exclude = await readSmall(fs, fs.join(repo, ".git", "info", "exclude"));
      if (exclude) outer.push([prefix, compileRules(splitLines(exclude))]);
    }
  }
  return new IgnoreEngine({
    extra: opts.ignore,
    defaults: opts.defaults,
    hidden,
    load: (folder, name) => readSmall(fs, fs.join(root, folder, name)),
    async marked(folder) {
      const base = fs.join(root, folder);
      if ((await fs.stat(fs.join(base, "pyvenv.cfg")))?.isFile) return true;
      try {
        return startsWith(await fs.readHead(fs.join(base, "CACHEDIR.TAG"), CACHEDIR_SIGNATURE.length), CACHEDIR_SIGNATURE);
      } catch {
        return false;
      }
    },
    outer,
  });
}

function memberEngine(members: Map<string, Uint8Array>, opts: TreeOptions): IgnoreEngine {
  return new IgnoreEngine({
    extra: opts.ignore,
    defaults: opts.defaults,
    hidden: opts.hidden,
    async load(folder, name) {
      const data = members.get(folder ? `${folder}/${name}` : name);
      if (data === undefined || data.length > MAX_IGNORE_FILE) return null;
      return decodeReplace(data);
    },
    async marked(folder) {
      const prefix = folder ? `${folder}/` : "";
      return members.has(`${prefix}pyvenv.cfg`) || startsWith(members.get(`${prefix}CACHEDIR.TAG`) ?? null, CACHEDIR_SIGNATURE);
    },
  });
}

function globFilter(opts: TreeOptions): ((path: string) => boolean) | null {
  if (opts.glob.length === 0) return null;
  const rules = compileRules(opts.glob);
  return (path) => {
    let result = false;
    for (const rule of rules) if (!rule.dirOnly && rule.regex.test(path)) result = !rule.negate;
    return result;
  };
}

// -- wildcard patterns -------------------------------------------------------------

const MAGIC = /[*?]|\[[^\]/]+\]/u;
const hasMagic = (component: string): boolean => MAGIC.test(component);

/** Whether `text` is a wildcard pattern: a segment with `*`, `?` or `[...]`. */
export function looksLikeGlob(text: string): boolean {
  return text.replaceAll("\\", "/").split("/").some(hasMagic);
}

/** `[static base, remaining segments]` of a pattern. */
export function splitPattern(pattern: string): [string, string[]] {
  const parts = pattern.replaceAll("\\", "/").split("/");
  let first = parts.slice(0, -1).findIndex(hasMagic);
  if (first === -1) first = parts.length - 1;
  let base = parts.slice(0, first).join("/");
  if (base === "" && parts[0] === "" && first > 0) base = "/";
  return [base, parts.slice(first)];
}

function validRegex(source: string): boolean {
  try {
    new RegExp(source, "u");
    return true;
  } catch {
    return false;
  }
}

const escapeChar = (c: string): string => (/[\\^$.*+?()[\]{}|/]/u.test(c) ? `\\${c}` : c);

function componentRegex(component: string, hidden: boolean): string {
  let out = "";
  let i = 0;
  while (i < component.length) {
    const c = component[i]!;
    if (c === "*") out += "[^/]*";
    else if (c === "?") out += "[^/]";
    else if (c === "[") {
      const from = component[i + 1] === "!" || component[i + 1] === "^" ? i + 2 : i + 1;
      const j = component.indexOf("]", from);
      let body = j !== -1 ? component.slice(i + 1, j) : "";
      if (body.startsWith("!") || body.startsWith("^")) body = `^${body.slice(1)}`;
      const group = `[${body.replaceAll("\\", "\\\\")}]`;
      if (j === -1 || !validRegex(group)) out += escapeChar(c);
      else {
        out += group;
        i = j;
      }
    } else out += escapeChar(c);
    i++;
  }
  if (!hidden && !component.startsWith(".") && hasMagic(component)) out = `(?!\\.)${out}`;
  return out;
}

/** Whole-path regex for paths relative to a pattern's static base. */
export function patternRegex(components: readonly string[], hidden: boolean): RegExp {
  const dirs = hidden ? "(?:[^/]+/)*" : "(?:(?!\\.)[^/]+/)*";
  let regex = "";
  components.forEach((comp, i) => {
    const last = i === components.length - 1;
    if (comp === "**") regex += dirs + (last ? `${hidden ? "" : "(?!\\.)"}[^/]+` : "");
    else regex += componentRegex(comp, hidden) + (last ? "" : "/");
  });
  return new RegExp(`^(?:${regex})$`, "su");
}

function couldMatch(folder: string, components: readonly string[], hidden: boolean): boolean {
  const parts = folder.split("/");
  for (let i = 0; i < Math.min(parts.length, components.length); i++) {
    if (!new RegExp(`^(?:${componentRegex(components[i]!, hidden)})$`, "su").test(parts[i]!)) return false;
  }
  return true;
}

// -- listing -------------------------------------------------------------------------

interface Candidate {
  rel: string;
  path: string;
  size: number;
}

export const MAX_SCAN_ENTRIES_DEFAULT = 200_000;

interface ListOptions {
  pattern?: RegExp;
  patternDepth?: number | undefined;
  patternComponents?: readonly string[] | undefined;
  hiddenDirs?: boolean;
  maxScan: number;
}

async function listFolder(fs: FileSystem, root: string, opts: TreeOptions, report: TreeReport, list: ListOptions): Promise<Candidate[]> {
  const hidden = list.hiddenDirs ?? opts.hidden;
  const engine = await folderEngine(fs, root, opts, hidden);
  const keepGlob = globFilter(opts);
  const rootReal = await fs.realpath(root);
  const candidates: Candidate[] = [];
  let scanned = 0;
  const stack: string[] = [""];
  while (stack.length > 0) {
    const folder = stack.pop()!;
    let entries;
    try {
      entries = (await fs.readdir(folder ? fs.join(root, folder) : root)).sort((a, b) => comparePoints(a.name, b.name));
    } catch {
      report.skip(UNREADABLE, folder, true);
      continue;
    }
    const subfolders: string[] = [];
    for (const entry of entries) {
      scanned++;
      if (scanned > list.maxScan) {
        report.scanCapped = true;
        return candidates;
      }
      const rel = folder ? `${folder}/${entry.name}` : entry.name;
      const full = fs.join(root, rel);
      if (entry.isDir) {
        if (list.patternDepth !== undefined && rel.split("/").length >= list.patternDepth) continue;
        if (list.patternComponents !== undefined && !couldMatch(rel, list.patternComponents, hidden)) continue;
        const reason = await engine.check(rel, true);
        if (reason) report.skip(reason, rel, true);
        else if (list.pattern === undefined && !opts.recursive) report.skip(NOT_RECURSIVE, rel, true);
        else subfolders.push(rel);
        continue;
      }
      if (list.pattern !== undefined && !list.pattern.test(rel)) continue;
      if (entry.isSymlink) {
        let real: string | null = null;
        try {
          real = await fs.realpath(full);
        } catch {
          real = null;
        }
        if (real === null || fs.inside(real, rootReal) === null) {
          report.skip(SYMLINK, rel);
          continue;
        }
        if ((await fs.stat(full))?.isDir) continue; // a folder inside the tree: read it there
      }
      const info = await fs.stat(full);
      if (info === null) {
        report.skip(UNREADABLE, rel);
        continue;
      }
      if (!info.isFile) {
        report.skip(SPECIAL, rel);
        continue;
      }
      const reason = await engine.check(rel, false);
      if (reason) {
        report.skip(reason, rel);
        continue;
      }
      if (keepGlob && !keepGlob(rel)) {
        report.skip(GLOB_OPTION, rel);
        continue;
      }
      candidates.push({ rel, path: full, size: info.size });
    }
    stack.push(...subfolders.reverse());
  }
  return candidates;
}

// -- reading within limits -----------------------------------------------------------

class Budget {
  filesLeft: number | null;
  bytesLeft: number | null;

  readonly report: TreeReport;

  constructor(opts: TreeOptions, report: TreeReport) {
    this.report = report;
    this.filesLeft = opts.maxFiles || null;
    this.bytesLeft = opts.maxSize || null;
  }

  take(size: number): boolean {
    if (this.filesLeft !== null && this.filesLeft <= 0) return this.#hit("max_files");
    if (this.bytesLeft !== null && size > this.bytesLeft) return this.#hit("max_size");
    if (this.filesLeft !== null) this.filesLeft--;
    if (this.bytesLeft !== null) this.bytesLeft -= size;
    return true;
  }

  refund(size: number): void {
    if (this.filesLeft !== null) this.filesLeft++;
    if (this.bytesLeft !== null) this.bytesLeft += size;
  }

  #hit(limit: "max_files" | "max_size"): false {
    this.report.notRead++;
    this.report.limit ??= limit;
    return false;
  }
}

/** Members of an archive through the skip rules and the limits. */
async function expandMembers(archiveRel: string, data: Uint8Array, opts: TreeOptions, report: TreeReport, budget: Budget): Promise<SourceFile[]> {
  const members = await explodeArchive("", data);
  const engine = memberEngine(new Map(members.map((m) => [m.name, m.data])), opts);
  const keepGlob = globFilter(opts);
  const out: SourceFile[] = [];
  for (const { name, data: content } of members) {
    const shown = archiveRel ? `${archiveRel}/${name}` : name;
    const reason = (await engine.checkPath(name)) ?? engine.checkContent(name, content);
    if (reason) {
      report.skip(reason, shown);
      continue;
    }
    if (keepGlob && !keepGlob(name)) {
      report.skip(GLOB_OPTION, shown);
      continue;
    }
    if (!budget.take(content.length)) continue;
    out.push({ name: shown, data: content });
  }
  return out;
}

async function readTree(fs: FileSystem, candidates: Candidate[], opts: TreeOptions, report: TreeReport): Promise<SourceFile[]> {
  const budget = new Budget(opts, report);
  const contents = new IgnoreEngine({ extra: opts.ignore, defaults: opts.defaults });
  const out: SourceFile[] = [];
  for (const candidate of candidates) {
    if (!opts.files) {
      if (budget.take(candidate.size)) report.entries.push({ path: candidate.rel, size: candidate.size });
      continue;
    }
    if (!budget.take(candidate.size)) continue;
    let data: Uint8Array;
    try {
      data = await fs.readFile(candidate.path);
    } catch {
      report.skip(UNREADABLE, candidate.rel);
      continue;
    }
    const reason = contents.checkContent(candidate.rel, data);
    if (reason) {
      report.skip(reason, candidate.rel);
      budget.refund(candidate.size);
      continue;
    }
    if (isArchiveName(candidate.rel)) {
      // The archive took one slot; its members are what counts.
      budget.refund(candidate.size);
      const members = await expandMembers(candidate.rel, data, opts, report, budget);
      report.entries.push({ path: candidate.rel, size: candidate.size, members: members.length });
      out.push(...members);
    } else {
      report.entries.push({ path: candidate.rel, size: data.length });
      out.push({ name: candidate.rel, data });
    }
  }
  return out;
}

// -- entry points --------------------------------------------------------------------

async function attachGit(fs: FileSystem, report: TreeReport, root: string): Promise<void> {
  const repo = await findRepoRoot(fs, root);
  if (repo !== null) report.git = await readGitInfo(fs, repo);
}

/** A folder on disk. */
export async function readFolder(
  fs: FileSystem,
  path: string,
  opts: TreeOptions,
  label: string,
  maxScan: number,
  kind: TreeKind = "folder",
  rootName?: string,
): Promise<[SourceFile[], TreeReport]> {
  const root = await fs.realpath(path);
  const report = new TreeReport(label, kind, rootName ?? (fs.basename(root) || root), opts);
  const candidates = await listFolder(fs, root, opts, report, { maxScan });
  const files = await readTree(fs, candidates, opts, report);
  await attachGit(fs, report, root);
  return [files, report];
}

/** An archive given directly (by name). */
export async function readArchive(name: string, data: Uint8Array, opts: TreeOptions, label: string): Promise<[SourceFile[], TreeReport]> {
  const report = new TreeReport(label, "archive", name, opts);
  const budget = new Budget(opts, report);
  if (!opts.files) {
    const members = await explodeArchive("", data);
    const engine = memberEngine(new Map(members.map((m) => [m.name, m.data])), opts);
    for (const m of members) {
      const reason = (await engine.checkPath(m.name)) ?? engine.checkContent(m.name, m.data);
      if (reason) report.skip(reason, m.name);
      else if (budget.take(m.data.length)) report.entries.push({ path: m.name, size: m.data.length });
    }
    return [[], report];
  }
  const members = await expandMembers(name, data, opts, report, budget);
  for (const m of members) report.entries.push({ path: m.name.slice(name.length + 1), size: m.data.length });
  return [members, report];
}

const RULE_REASONS = new Set(["ignore option", "secret", "generated", "hidden", "ignore file"]);

/** Files matching a wildcard pattern, named relative to its static base. */
export async function readPattern(fs: FileSystem, pattern: string, opts: TreeOptions, maxScan: number): Promise<[SourceFile[], TreeReport]> {
  const [base, components] = splitPattern(pattern);
  const report = new TreeReport(pattern, "pattern", base || ".", opts);
  const rootInfo = await fs.stat(base || ".");
  if (!rootInfo?.isDir) throw new Error(await noMatchMessage(fs, pattern, report));
  const root = await fs.realpath(base || ".");
  const needsHidden = opts.hidden || components.some((c) => c.startsWith("."));
  const globstar = components.includes("**");
  const candidates = await listFolder(fs, root, opts, report, {
    pattern: patternRegex(components, opts.hidden),
    patternDepth: globstar ? undefined : components.length,
    patternComponents: globstar ? undefined : components,
    hiddenDirs: needsHidden ? true : opts.hidden,
    maxScan,
  });
  if (candidates.length === 0 && opts.files) throw new Error(await noMatchMessage(fs, pattern, report));
  const files = await readTree(fs, candidates, opts, report);
  await attachGit(fs, report, root);
  return [files, report];
}

async function noMatchMessage(fs: FileSystem, pattern: string, report: TreeReport): Promise<string> {
  let message = `Glob pattern matched no files: ${pattern}`;
  const counts = [...report.skipped]
    .filter(([reason]) => RULE_REASONS.has(reason))
    .map(([reason, s]) => `${reason}: ${s.files + s.folders}`)
    .join(", ");
  if (counts) {
    message +=
      ` — skipped: ${counts} (matching files, or folders that were not searched); ` +
      "add [ignore: none] (and [hidden: true] for dot files) to include them";
  }
  void fs;
  return message;
}

export { decide };
