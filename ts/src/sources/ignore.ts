/**
 * Which files of a tree are skipped, and why (contract/reading.md, "Skip
 * rules"): version control, the `ignore` option, secrets, generated
 * files, hidden files, ignore files.
 *
 * @internal
 */

import { READING } from "../generated/reading.ts";
import { SPACE_CLASS, strip } from "../text.ts";

export const VCS = "vcs";
export const OPTION = "ignore option";
export const SECRET = "secret";
export const GENERATED = "generated";
export const HIDDEN = "hidden";
export const IGNORE_FILE = "ignore file";

const VCS_DIRS = new Set<string>(READING.vcs_dirs);
export const IGNORE_FILES: readonly string[] = READING.ignore_files;
export const CACHEDIR_SIGNATURE = new TextEncoder().encode(READING.cachedir_signature);

/** One compiled gitignore line. */
export interface Rule {
  regex: RegExp;
  negate: boolean;
  dirOnly: boolean;
  text: string;
}

/** Python's `re.escape` for the characters JavaScript (with the `u` flag) needs escaped. */
export function escapeRegex(ch: string): string {
  return /[\\^$.*+?()[\]{}|/]/u.test(ch) ? `\\${ch}` : ch;
}

/** A `[...]` class starting at `i`: `[regex, next index]`, or `null` when unclosed. */
function translateClass(pattern: string, i: number): [string, number] | null {
  let j = i + 1;
  if (j < pattern.length && (pattern[j] === "!" || pattern[j] === "^")) j++;
  if (j < pattern.length && pattern[j] === "]") j++;
  while (j < pattern.length && pattern[j] !== "]") j++;
  if (j >= pattern.length) return null;
  let body = pattern.slice(i + 1, j);
  const negate = body.startsWith("!") || body.startsWith("^");
  if (negate) body = body.slice(1);
  body = body.replaceAll("\\", "\\\\").replaceAll("/", "");
  if (body.startsWith("]")) body = `\\${body}`;
  return [`${negate ? "[^/" : "["}${body}]`, j + 1];
}

function segmentRegex(segment: string): string {
  // UTF-16 indices: a surrogate pair passes through as two literal halves,
  // which the `u` flag reads back as the one character.
  let out = "";
  let i = 0;
  while (i < segment.length) {
    const c = segment[i]!;
    if (c === "\\" && i + 1 < segment.length) {
      out += escapeRegex(segment[i + 1]!);
      i += 2;
    } else if (c === "*") {
      while (i < segment.length && segment[i] === "*") i++;
      out += "[^/]*";
    } else if (c === "?") {
      out += "[^/]";
      i++;
    } else if (c === "[") {
      const translated = translateClass(segment, i);
      if (translated) {
        out += translated[0];
        i = translated[1];
      } else {
        out += escapeRegex(c);
        i++;
      }
    } else {
      out += escapeRegex(c);
      i++;
    }
  }
  return out;
}

/** The regex (whole-path) of a gitignore pattern body (no `!`, no trailing `/`). */
export function translateGitignore(pattern: string): string {
  const anchored = pattern.startsWith("/") || pattern.replace(/\/+$/u, "").includes("/");
  const parts = pattern.replace(/^\/+/u, "").split("/");
  let regex = "";
  parts.forEach((part, index) => {
    const last = index === parts.length - 1;
    if (part === "**") {
      regex += last ? (index === 0 ? ".*" : ".+") : "(?:[^/]+/)*";
      return;
    }
    regex += segmentRegex(part);
    if (!last) regex += "/";
  });
  return anchored ? regex : `(?:.*/)?${regex}`;
}

const TRAILING_SPACE = new RegExp(`(?<!\\\\)${SPACE_CLASS}+$`, "u");

/** One line of an ignore file; `null` for blanks, comments and lines that do not compile. */
export function compileRule(line: string): Rule | null {
  const text = line.replace(/\n$/u, "").replace(/\r$/u, "");
  const stripped = text.replace(TRAILING_SPACE, "");
  if (!stripped || stripped.startsWith("#")) return null;
  let body = stripped;
  const negate = body.startsWith("!");
  if (negate) body = body.slice(1);
  else if (body.startsWith("\\!") || body.startsWith("\\#")) body = body.slice(1);
  const dirOnly = body.endsWith("/");
  body = body.replace(/\/+$/u, "");
  if (!body) return null;
  try {
    return { regex: new RegExp(`^(?:${translateGitignore(body)})$`, "su"), negate, dirOnly, text: stripped };
  } catch {
    return null;
  }
}

export function compileRules(lines: Iterable<string>): Rule[] {
  const out: Rule[] = [];
  for (const line of lines) {
    const rule = compileRule(line);
    if (rule) out.push(rule);
  }
  return out;
}

/** Python's `str.splitlines()`. */
export function splitLines(text: string): string[] {
  const lines = text.split(/\r\n|[\n\r\u000b\u000c\u001c\u001d\u001e\u0085\u2028\u2029]/u);
  if (lines.length > 0 && lines.at(-1) === "") lines.pop();
  return lines;
}

/** An option value as patterns: a list, or text separated by commas or line breaks. */
export function splitPatterns(value: unknown): string[] {
  if (value === undefined || value === null) return [];
  const list = typeof value === "string" ? value.split(/[,\n]/u) : Array.isArray(value) ? value.map(String) : [String(value)];
  return list.filter((p) => p && strip(p)).map(strip);
}

/** The last matching rule: `true` skipped, `false` kept, `null` undecided. */
export function decide(rules: readonly Rule[], path: string, isDir: boolean): boolean | null {
  let result: boolean | null = null;
  for (const rule of rules) {
    if (rule.dirOnly && !isDir) continue;
    if (rule.regex.test(path)) result = !rule.negate;
  }
  return result;
}

const SECRET_RULES = compileRules(READING.secret_patterns);
const GENERATED_RULES = compileRules(READING.generated_patterns);

const KEY_START = /^(?:\xef\xbb\xbf)?[\t\n\u000b\u000c\r ]*(?:-----BEGIN [A-Z0-9 ]*PRIVATE KEY(?: BLOCK)?-----|PuTTY-User-Key-File-\d)/u;

/** Whether `data` is a private key file, by its first 256 bytes. */
export function looksLikeKey(data: Uint8Array): boolean {
  // Latin-1: one character per byte, as Python's bytes regex sees them.
  let head = "";
  for (let i = 0; i < Math.min(256, data.length); i++) head += String.fromCharCode(data[i]!);
  return KEY_START.test(head);
}

export function isSecret(path: string): boolean {
  return decide(SECRET_RULES, path, false) === true;
}

export interface EngineOptions {
  extra?: readonly string[];
  defaults?: boolean;
  hidden?: boolean;
  /** Ignore-file text in a folder of the tree (`""` = root), or `null`. */
  load?: (folder: string, name: string) => Promise<string | null>;
  /** Whether a folder is generated by its marker files. */
  marked?: (folder: string) => Promise<boolean>;
  /** Rules of ignore files above the root, with the prefix that makes a path relative to them; closest first. */
  outer?: readonly (readonly [prefix: string, rules: readonly Rule[]])[];
}

export class IgnoreEngine {
  readonly defaults: boolean;
  readonly hidden: boolean;
  readonly #extra: Rule[];
  readonly #load: EngineOptions["load"];
  readonly #marked: EngineOptions["marked"];
  readonly #outer: NonNullable<EngineOptions["outer"]>;
  readonly #cache = new Map<string, Rule[]>();

  constructor({ extra = [], defaults = true, hidden = false, load, marked, outer = [] }: EngineOptions = {}) {
    this.defaults = defaults;
    this.hidden = hidden;
    this.#extra = compileRules(extra);
    this.#load = load;
    this.#marked = marked;
    this.#outer = outer;
  }

  async #folderRules(folder: string): Promise<Rule[]> {
    let rules = this.#cache.get(folder);
    if (rules === undefined) {
      rules = [];
      if (this.#load) {
        for (const name of IGNORE_FILES) {
          const text = await this.#load(folder, name);
          if (text) rules.push(...compileRules(splitLines(text)));
        }
      }
      this.#cache.set(folder, rules);
    }
    return rules;
  }

  /** Why `path` (relative, `/`-separated) is skipped, or `null`. Its parent folders are already checked. */
  async check(path: string, isDir: boolean): Promise<string | null> {
    const name = path.slice(path.lastIndexOf("/") + 1);
    if (isDir && VCS_DIRS.has(name)) return VCS;
    const decided = decide(this.#extra, path, isDir);
    if (decided !== null) return decided ? OPTION : null;
    if (!this.defaults) return null;
    if (decide(SECRET_RULES, path, isDir)) return SECRET;
    if (decide(GENERATED_RULES, path, isDir)) return GENERATED;
    if (isDir && this.#marked && (await this.#marked(path))) return GENERATED;
    if (!this.hidden && name.startsWith(".")) return HIDDEN;
    return (await this.#ignoredByFiles(path, isDir)) ? IGNORE_FILE : null;
  }

  async #ignoredByFiles(path: string, isDir: boolean): Promise<boolean> {
    const parts = path.split("/");
    for (let depth = parts.length - 1; depth >= 0; depth--) {
      const rules = await this.#folderRules(parts.slice(0, depth).join("/"));
      if (rules.length > 0) {
        const decided = decide(rules, parts.slice(depth).join("/"), isDir);
        if (decided !== null) return decided;
      }
    }
    for (const [prefix, rules] of this.#outer) {
      const decided = decide(rules, prefix + path, isDir);
      if (decided !== null) return decided;
    }
    return false;
  }

  /** `"secret"` for a private key, whatever its name, unless the options keep it. */
  checkContent(path: string, data: Uint8Array): string | null {
    if (!this.defaults || decide(this.#extra, path, false) === false) return null;
    return looksLikeKey(data) ? SECRET : null;
  }

  /** Check a path and every parent folder (flat lists: archive members). */
  async checkPath(path: string): Promise<string | null> {
    const parts = path.split("/");
    for (let depth = 1; depth < parts.length; depth++) {
      const reason = await this.check(parts.slice(0, depth).join("/"), true);
      if (reason) return reason;
    }
    return this.check(path, false);
  }
}
