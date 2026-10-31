/**
 * The overview artifact of a folder, repository, pattern or archive
 * (contract/reading.md, "The overview").
 *
 * @internal
 */

import { READING } from "../generated/reading.ts";
import { commas, fixed1 } from "../text.ts";
import type { Artifact } from "../types.ts";
import { gitSummary } from "./git.ts";
import { VCS } from "./ignore.ts";
import type { TreeReport } from "./tree.ts";

const REASONS: Record<string, readonly [string, string]> = READING.skip_reasons as unknown as Record<string, readonly [string, string]>;
const KINDS: Record<string, string> = READING.tree_kinds;

/** Bytes in powers of 1000: `999 B`, `48.2 KB`, `3.4 MB`. */
export function humanSize(size: number): string {
  let value = size;
  for (const unit of ["B", "KB", "MB", "GB"]) {
    if (value < 1000 || unit === "GB") return unit === "B" ? `${Math.trunc(value)} B` : `${fixed1(value)} ${unit}`;
    value /= 1000;
  }
  return `${size} B`;
}

const count = (n: number, word: string): string => `${commas(n)} ${word}${n === 1 ? "" : "s"}`;

type Node = Map<string, Node | string>;

/** A `tree`-style listing of `[path, note]` pairs, in order. */
export function renderTree(root: string, paths: readonly (readonly [string, string])[]): string {
  const tree: Node = new Map();
  for (const [path, note] of paths) {
    let node = tree;
    const parts = path.split("/");
    for (const part of parts.slice(0, -1)) {
      const key = `${part}/`;
      let child = node.get(key);
      if (!(child instanceof Map)) {
        child = new Map();
        node.set(key, child);
      }
      node = child;
    }
    node.set(parts.at(-1)!, note);
  }
  const lines = [`${root.replace(/\/+$/u, "")}/`];
  const walk = (node: Node, prefix: string): void => {
    const items = [...node];
    items.forEach(([name, child], i) => {
      const last = i === items.length - 1;
      const branch = last ? "└── " : "├── ";
      if (child instanceof Map) {
        lines.push(prefix + branch + name);
        walk(child, prefix + (last ? "    " : "│   "));
      } else lines.push(prefix + branch + name + (child ? `  (${child})` : ""));
    });
  };
  walk(tree, "");
  return lines.join("\n");
}

function skippedLines(report: TreeReport): string[] {
  const lines: string[] = [];
  for (const [reason, s] of report.skipped) {
    if (reason === VCS) continue;
    const [name, remedy] = REASONS[reason] ?? [reason, ""];
    const parts: string[] = [];
    if (s.folders) parts.push(count(s.folders, "folder"));
    if (s.files) parts.push(count(s.files, "file"));
    let examples = s.examples.join(", ");
    if (s.files + s.folders > s.examples.length) examples += ", …";
    let line = `- ${name}: ${parts.join(" and ")} (${examples})`;
    if (remedy) line += ` — ${remedy}`;
    lines.push(line);
  }
  return lines;
}

function limitLine(report: TreeReport, maxScan: number): string | null {
  if (report.scanCapped) {
    return `Stopped looking after ${commas(maxScan)} entries: the folder is larger than that. Point at a subfolder or use a pattern.`;
  }
  if (report.limit === null) return null;
  const value = report.limit === "max_size" ? report.options.maxSize : report.options.maxFiles;
  const shown = report.limit === "max_size" ? humanSize(value) : commas(value);
  return `Stopped at ${report.limit}: ${shown} — ${count(report.notRead, "more file")} not read. Raise it with [${report.limit}: ...] (0 = no limit).`;
}

export function wantsTree(report: TreeReport): boolean {
  if (!report.options.files) return true;
  if (report.options.tree === "auto") return report.kind === "folder" || report.kind === "repo";
  return report.options.tree;
}

export function needsOverview(report: TreeReport): boolean {
  return (
    wantsTree(report) ||
    report.limit !== null ||
    report.scanCapped ||
    report.warnings.length > 0 ||
    (report.filesRead === 0 && report.skipped.size > 0)
  );
}

export function overviewArtifact(report: TreeReport, maxScan: number): Artifact {
  const n = report.filesRead;
  let header = `${KINDS[report.kind] ?? "Folder"} ${report.label}`;
  header += report.options.files
    ? ` — ${count(n, "file")} read, ${humanSize(report.totalBytes)}`
    : ` — ${count(n, "file")}, ${humanSize(report.totalBytes)} (contents not read: files: false)`;
  const lines = [header];
  if (report.git) lines.push(`Git: ${gitSummary(report.git)}`);
  const limit = limitLine(report, maxScan);
  if (limit) lines.push(limit);
  const skipped = skippedLines(report);
  if (skipped.length > 0) lines.push("Skipped:", ...skipped);
  if (wantsTree(report)) {
    const entries = report.entries.map((e) => [e.path, e.members !== undefined ? count(e.members, "file") : ""] as const);
    lines.push("", entries.length > 0 ? renderTree(report.rootName, entries) : "(no files)");
  }
  const warnings = [...report.warnings];
  if (limit) warnings.push(limit);
  const extra: Record<string, unknown> = {
    kind: report.kind,
    root: report.rootName,
    files: n,
    bytes: report.totalBytes,
    skipped: Object.fromEntries([...report.skipped].map(([r, s]) => [r, { files: s.files, folders: s.folders, examples: s.examples }])),
  };
  if (report.limit) {
    extra["limit"] = report.limit;
    extra["not_read"] = report.notRead;
  }
  if (report.scanCapped) extra["scan_capped"] = true;
  if (report.git) extra["git"] = { branch: report.git.branch, commit: report.git.commit, remote: report.git.remote };
  const meta: Artifact["meta"] = { source: report.label, kind: "directory", extra };
  if (warnings.length > 0) meta.warnings = warnings;
  return { text: lines.join("\n"), images: [], audio: [], video: [], meta };
}
