/**
 * The printed summary of a result (contract/presenting.md, "The printed
 * summary"): one line, then its errors, warnings and notes. Never text or
 * bytes.
 *
 * @internal
 */

import { estimateTokens } from "./present.ts";
import { commas, cpLength, fixed1 } from "./text.ts";
import type { Artifact, ErrorCode, ErrorInfo } from "./types.ts";

const MESSAGE_CHARS = 160;
const MAX_LINES = 10;

const plural = (n: number, noun: string): string => (n === 1 ? `${n} ${noun}` : `${n} ${noun}s`);

function compact(n: number): string {
  let value: number;
  let suffix: string;
  if (n >= 1_000_000) [value, suffix] = [n / 1_000_000, "M"];
  else if (n >= 1000) [value, suffix] = [n / 1000, "k"];
  else return String(n);
  const text = fixed1(value);
  return `${text.endsWith(".0") ? text.slice(0, -2) : text}${suffix}`;
}

/** Cut a long message in the middle, keeping its end (where the remedy is). */
export function clipMessage(message: string): string {
  const points = Array.from(message);
  if (points.length <= MESSAGE_CHARS) return message;
  const head = Math.floor((MESSAGE_CHARS - 1) / 2);
  const tail = MESSAGE_CHARS - 1 - head;
  return `${points.slice(0, head).join("")}…${points.slice(-tail).join("")}`;
}

function collapse(entries: [source: string, content: string][]): string[] {
  const order = new Map<string, string[]>();
  for (const [source, content] of entries) {
    const list = order.get(content);
    if (list) list.push(source);
    else order.set(content, [source]);
  }
  return [...order].map(([content, sources]) =>
    sources.length === 1 ? `${sources[0]}: ${content}` : `${content} (x${sources.length})`,
  );
}

/** `{ source, code, message }` for each failed artifact. */
export function errorsOf(artifacts: readonly Artifact[]): ErrorInfo[] {
  const out: ErrorInfo[] = [];
  for (const a of artifacts) {
    const error = a.meta?.error;
    if (typeof error === "object" && error !== null && !Array.isArray(error)) {
      out.push({
        source: a.meta.source || "(unknown)",
        code: (error.code || "") as ErrorCode | "",
        message: error.message || "",
      });
    }
  }
  return out;
}

/** The summary line's content: `2 artifacts | 14,210 chars | ~4.1k tokens | 3 images`. */
export function summaryLine(artifacts: readonly Artifact[]): string {
  let chars = 0;
  for (const a of artifacts) chars += cpLength(a.text || "");
  const estimate = estimateTokens(artifacts);
  let tokens = `~${compact(estimate.total)} tokens`;
  if (estimate.images) tokens += ` (images ~${compact(estimate.images)})`;
  const parts = [plural(artifacts.length, "artifact"), `${commas(chars)} chars`, tokens];
  const images = artifacts.reduce((n, a) => n + (a.images?.length ?? 0), 0);
  if (images) parts.push(plural(images, "image"));
  const errors = errorsOf(artifacts).length;
  if (errors) parts.push(plural(errors, "error"));
  return parts.join(" | ");
}

/** The whole summary: the line, then errors (`!`), warnings (`!`) and notes (`*`). */
export function summary(artifacts: readonly Artifact[]): string {
  const lines = [`<Artifacts: ${summaryLine(artifacts)}>`];
  const section = (entries: [string, string][], mark: string, overflow: (n: number) => string): void => {
    const collapsed = collapse(entries);
    lines.push(...collapsed.slice(0, MAX_LINES).map((l) => `  ${mark} ${l}`));
    const hidden = collapsed.length - MAX_LINES;
    if (hidden > 0) lines.push(overflow(hidden));
  };
  section(
    errorsOf(artifacts).map((e) => [e.source, `${e.code} — ${clipMessage(e.message)}`]),
    "!",
    (n) => `  … +${plural(n, "more error")} (see .errors)`,
  );
  section(
    artifacts.flatMap((a) => (a.meta?.warnings ?? []).map((w): [string, string] => [a.meta.source ?? "?", clipMessage(w)])),
    "!",
    (n) => `  … +${plural(n, "more warning")}`,
  );
  section(
    artifacts.filter((a) => a.meta?.note).map((a): [string, string] => [a.meta.source ?? "?", clipMessage(a.meta.note!)]),
    "*",
    (n) => `  … +${plural(n, "more note")}`,
  );
  return lines.join("\n");
}

/** The message of the error that lists failures. */
export function errorSummary(errors: readonly ErrorInfo[]): string {
  const lines = errors.map((e) => `${e.source}: ${e.code} — ${e.message}`);
  if (lines.length === 1) return lines[0]!;
  return `${lines.length} inputs failed:\n${lines.map((l) => `  ${l}`).join("\n")}`;
}
