/**
 * The `source[key: value, ...]` syntax (contract/dsl-grammar.md): a pure
 * function from a string to its source and raw typed options. No aliases,
 * no validation; that is option resolution's job.
 */

import { SPACE_CLASS, strip } from "./text.ts";

/** A raw option value, as the syntax types it. A range is `[first, last]`. */
export type DslValue = string | number | boolean | readonly [number, number];

const INT = /^-?[0-9]+$/u;
const FLOAT = /^-?(?:[0-9]+\.[0-9]*|\.[0-9]+)$/u;
const RANGE = new RegExp(`^([0-9]+)${SPACE_CLASS}*-${SPACE_CLASS}*([0-9]+)$`, "u");
const KEY_SEPARATORS = new RegExp(`(?:${SPACE_CLASS}|-)+`, "gu");

function normalizeKey(key: string): string {
  return strip(key).toLowerCase().replace(KEY_SEPARATORS, "_");
}

/**
 * An integer, or its text when JavaScript cannot hold it exactly (past
 * ±2^53 − 1): kept as written rather than changed.
 */
function integer(text: string): number | string {
  const n = Number(text);
  return Number.isSafeInteger(n) ? n : text;
}

/** Type a raw value: quoted text, boolean, integer, float, range, else text. */
export function typeValue(raw: string): DslValue {
  const value = strip(raw);
  if (value.length >= 2 && value[0] === value.at(-1) && (value[0] === '"' || value[0] === "'")) {
    return value.slice(1, -1);
  }
  const lowered = value.toLowerCase();
  if (lowered === "true" || lowered === "yes" || lowered === "on") return true;
  if (lowered === "false" || lowered === "no" || lowered === "off") return false;
  if (INT.test(value)) return integer(value);
  if (FLOAT.test(value)) return Number(value);
  const range = RANGE.exec(value);
  if (range) {
    const first = integer(range[1]!);
    const last = integer(range[2]!);
    if (typeof first === "number" && typeof last === "number") return [first, last];
  }
  return value;
}

function splitOutsideQuotes(text: string, separator: string): string[] {
  const parts: string[] = [];
  let current = "";
  let quote: string | null = null;
  for (const ch of text) {
    if (quote === null && (ch === '"' || ch === "'")) quote = ch;
    else if (ch === quote) quote = null;
    else if (ch === separator && quote === null) {
      parts.push(current);
      current = "";
      continue;
    }
    current += ch;
  }
  parts.push(current);
  return parts;
}

function colonOutsideQuotes(segment: string): number {
  let quote: string | null = null;
  for (let i = 0; i < segment.length; i++) {
    const ch = segment[i]!;
    if (quote === null && (ch === '"' || ch === "'")) quote = ch;
    else if (ch === quote) quote = null;
    else if (ch === ":" && quote === null) return i;
  }
  return -1;
}

/**
 * An option value from the string: typed, and as written. An option of
 * type `str` takes the text (`[password: 007]` is `"007"`), every other
 * type the typed value (contract/reading.md, "Options").
 *
 * @internal
 */
export class Written {
  readonly value: DslValue;
  readonly text: string;

  constructor(value: DslValue, text: string) {
    this.value = value;
    this.text = text;
  }

  toString(): string {
    return this.text;
  }

  toJSON(): DslValue {
    return this.value;
  }
}

function unquote(raw: string): string {
  const value = strip(raw);
  if (value.length >= 2 && value[0] === value.at(-1) && (value[0] === '"' || value[0] === "'")) return value.slice(1, -1);
  return value;
}

/** {@link parseDsl} with each value's text as written. @internal */
export function parseDslWritten(input: string): [source: string, options: Record<string, Written>] {
  const [source, splits] = split(input);
  return [source, Object.fromEntries(splits.map(([k, v]) => [k, new Written(typeValue(v), unquote(v))]))];
}

/**
 * Split an input into its source and raw options.
 *
 * @example
 * parseDsl("report.pdf[pages: 1-4, images: true]")
 * // ["report.pdf", { pages: [1, 4], images: true }]
 */
export function parseDsl(input: string): [source: string, options: Record<string, DslValue>] {
  const [source, splits] = split(input);
  const options: Record<string, DslValue> = {};
  for (const [key, value] of splits) options[key] = typeValue(value); // the last occurrence wins
  return [source, options];
}

function split(input: string): [string, [string, string][]] {
  const text = strip(input);
  if (!text.endsWith("]")) return [text, []];
  let depth = 0;
  let blockStart = -1;
  for (let i = text.length - 1; i >= 0; i--) {
    if (text[i] === "]") depth++;
    else if (text[i] === "[") {
      depth--;
      if (depth === 0) {
        blockStart = i;
        break;
      }
    }
  }
  if (blockStart === -1) return [text, []];
  const source = strip(text.slice(0, blockStart));
  const body = text.slice(blockStart + 1, -1);
  if (!strip(body)) return [source, []];
  const segments = splitOutsideQuotes(body, ",");
  if (segments.length > 1 && !strip(segments.at(-1)!)) segments.pop();
  const splits: [string, string][] = [];
  for (const segment of segments) {
    const colon = colonOutsideQuotes(segment);
    if (colon === -1) {
      if (splits.length === 0) return [text, []];
      const last = splits.at(-1)!;
      last[1] = `${last[1]},${segment}`;
      continue;
    }
    splits.push([segment.slice(0, colon), segment.slice(colon + 1)]);
  }
  return [source, splits.map(([k, v]) => [normalizeKey(k), v])];
}

function sameValue(a: DslValue, b: DslValue): boolean {
  if (Array.isArray(a) || Array.isArray(b)) return false;
  return a === b;
}

function formatValue(value: DslValue): string {
  if (typeof value === "boolean") return value ? "true" : "false";
  if (Array.isArray(value) && value.length === 2) return `${value[0]}-${value[1]}`;
  if (typeof value === "number") return String(value);
  const text = String(value);
  const needsQuotes =
    text !== strip(text) || text === "" || /[,[\]'"]/u.test(text) || !sameValue(typeValue(text), text);
  if (needsQuotes) {
    const quote = text.includes('"') ? "'" : '"';
    return `${quote}${text}${quote}`;
  }
  return text;
}

/**
 * The inverse of {@link parseDsl}: a source and raw options as one string.
 *
 * @example
 * formatDsl("report.pdf", { pages: [1, 4], images: true })
 * // "report.pdf[pages: 1-4, images: true]"
 */
export function formatDsl(source: string, options: Record<string, DslValue>): string {
  const entries = Object.entries(options);
  if (entries.length === 0) return source;
  return `${source}[${entries.map(([k, v]) => `${k}: ${formatValue(v)}`).join(", ")}]`;
}
