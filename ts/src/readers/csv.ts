/**
 * CSV and TSV (contract/processors.md, "CSV"): Python's `csv.Sniffer`
 * and `csv.reader` (excel dialect), ported, then a Markdown table.
 *
 * @internal
 */

import { errorArtifact, makeArtifact } from "../artifact.ts";
import { guessDecode } from "../decode.ts";
import type { ProcessorFn } from "../processors.ts";
import { CodePoints, isBlank } from "../text.ts";

// -- csv.Sniffer ---------------------------------------------------------------------

/** Python's `\w` (Unicode letters, digits, `_`), and its multiline `^` / `$` (only `\n` breaks a line). */
const W = "\\p{L}\\p{N}_";
const BOL = "(?:(?<![\\s\\S])|(?<=\\n))";
const EOL = "(?=\\n|(?![\\s\\S]))";

const QUOTE_PATTERNS = [
  `(?<delim>[^${W}\\n"'])(?<space> ?)(?<quote>["']).*?\\k<quote>\\k<delim>`,
  `(?:${BOL}|\\n)(?<quote>["']).*?\\k<quote>(?<delim>[^${W}\\n"'])(?<space> ?)`,
  `(?<delim>[^${W}\\n"'])(?<space> ?)(?<quote>["']).*?\\k<quote>(?:${EOL}|\\n)`,
  `(?:${BOL}|\\n)(?<quote>["']).*?\\k<quote>(?:${EOL}|\\n)`,
].map((p) => new RegExp(p, "gsu"));

/** The first key with the largest count (Python's `max(d, key=d.get)`). */
function argmax(counts: Map<string, number>): string {
  let best = "";
  let n = -Infinity;
  for (const [k, v] of counts) {
    if (v > n) {
      best = k;
      n = v;
    }
  }
  return best;
}

function guessQuoteAndDelimiter(data: string, delimiters: string): string | null {
  let matches: RegExpMatchArray[] = [];
  let pattern = 0;
  for (; pattern < QUOTE_PATTERNS.length; pattern++) {
    matches = [...data.matchAll(QUOTE_PATTERNS[pattern]!)];
    if (matches.length > 0) break;
  }
  if (matches.length === 0) return null;
  const delims = new Map<string, number>();
  for (const m of matches) {
    const key = m.groups?.["delim"];
    if (key && delimiters.includes(key)) delims.set(key, (delims.get(key) ?? 0) + 1);
  }
  if (delims.size === 0) return ""; // a single column of quoted data
  const delim = argmax(delims);
  return delim === "\n" ? "" : delim;
}

const PREFERRED = [",", "\t", ";", " ", ":"];

function count(line: string, ch: string): number {
  let n = 0;
  for (let i = 0; i < line.length; i++) if (line[i] === ch) n++;
  return n;
}

function guessDelimiter(sample: string, delimiters: string): string {
  const data = sample.split("\n").filter((l) => l !== "");
  const ascii = Array.from({ length: 127 }, (_, c) => String.fromCharCode(c));
  const chunkLength = Math.min(10, data.length);
  let iteration = 0;
  const charFrequency = new Map<string, Map<number, number>>();
  const modes = new Map<string, [number, number]>();
  const delims = new Map<string, [number, number]>();
  let start = 0;
  let end = chunkLength;
  while (start < data.length) {
    iteration++;
    for (const line of data.slice(start, end)) {
      for (const ch of ascii) {
        const meta = charFrequency.get(ch) ?? new Map<number, number>();
        const freq = count(line, ch);
        meta.set(freq, (meta.get(freq) ?? 0) + 1);
        charFrequency.set(ch, meta);
      }
    }
    for (const [ch, meta] of charFrequency) {
      const items = [...meta];
      if (items.length === 1 && items[0]![0] === 0) continue;
      if (items.length > 1) {
        let mode = items[0]!;
        for (const it of items) if (it[1] > mode[1]) mode = it;
        const rest = items.filter((it) => it !== mode).reduce((s, it) => s + it[1], 0);
        modes.set(ch, [mode[0], mode[1] - rest]);
      } else modes.set(ch, items[0]!);
    }
    const total = Math.min(chunkLength * iteration, data.length);
    let consistency = 1.0;
    const threshold = 0.9;
    while (delims.size === 0 && consistency >= threshold) {
      for (const [k, v] of modes) {
        if (v[0] > 0 && v[1] > 0 && v[1] / total >= consistency && delimiters.includes(k)) delims.set(k, v);
      }
      consistency -= 0.01;
    }
    if (delims.size === 1) return [...delims.keys()][0]!;
    start = end;
    end += chunkLength;
  }
  if (delims.size === 0) return "";
  for (const d of PREFERRED) if (delims.has(d)) return d;
  const items = [...delims].map(([k, v]) => [v, k] as const);
  items.sort((a, b) => a[0][0] - b[0][0] || a[0][1] - b[0][1] || (a[1] < b[1] ? -1 : a[1] > b[1] ? 1 : 0));
  return items.at(-1)![1];
}

/** Python's `csv.Sniffer().sniff(sample, delimiters).delimiter`, or `null` when it finds none. */
export function sniffDelimiter(sample: string, delimiters: string): string | null {
  let delimiter = guessQuoteAndDelimiter(sample, delimiters);
  if (!delimiter) delimiter = guessDelimiter(sample, delimiters);
  return delimiter || null;
}

// -- csv.reader (excel dialect) ------------------------------------------------------

export class CsvError extends Error {
  override name = "CsvError";
}

type State = "START_RECORD" | "START_FIELD" | "IN_FIELD" | "IN_QUOTED_FIELD" | "QUOTE_IN_QUOTED_FIELD" | "EAT_CRNL";
const END = null; // the end of a line, after its characters

/** Python's `csv.reader(io.StringIO(text), delimiter=delimiter)`, all rows. */
export function readCsv(text: string, delimiter: string): string[][] {
  const rows: string[][] = [];
  let state: State = "START_RECORD";
  let fields: string[] = [];
  let field = "";
  let fieldLen = 0;
  const save = (): void => {
    fields.push(field);
    field = "";
    fieldLen = 0;
  };
  const add = (c: string): void => {
    field += c;
    fieldLen++;
  };
  const step = (c: string | null): void => {
    switch (state) {
      case "START_RECORD":
        if (c === END) return;
        if (c === "\n" || c === "\r") {
          state = "EAT_CRNL";
          return;
        }
        state = "START_FIELD";
      // falls through
      case "START_FIELD":
        if (c === "\n" || c === "\r" || c === END) {
          save();
          state = c === END ? "START_RECORD" : "EAT_CRNL";
        } else if (c === '"') state = "IN_QUOTED_FIELD";
        else if (c === delimiter) save();
        else {
          add(c);
          state = "IN_FIELD";
        }
        return;
      case "IN_FIELD":
        if (c === "\n" || c === "\r" || c === END) {
          save();
          state = c === END ? "START_RECORD" : "EAT_CRNL";
        } else if (c === delimiter) {
          save();
          state = "START_FIELD";
        } else add(c);
        return;
      case "IN_QUOTED_FIELD":
        if (c === END) return;
        if (c === '"') state = "QUOTE_IN_QUOTED_FIELD";
        else add(c);
        return;
      case "QUOTE_IN_QUOTED_FIELD":
        if (c === '"') {
          add(c);
          state = "IN_QUOTED_FIELD";
        } else if (c === delimiter) {
          save();
          state = "START_FIELD";
        } else if (c === "\n" || c === "\r" || c === END) {
          save();
          state = c === END ? "START_RECORD" : "EAT_CRNL";
        } else {
          add(c);
          state = "IN_FIELD";
        }
        return;
      case "EAT_CRNL":
        if (c === "\n" || c === "\r") return;
        if (c === END) {
          state = "START_RECORD";
          return;
        }
        throw new CsvError("new-line character seen in unquoted field - do you need to open the file with newline=''?");
    }
  };
  // io.StringIO yields lines that end after each "\n".
  const lines = text.match(/[^\n]*\n|[^\n]+$/gu) ?? [];
  let i = 0;
  while (i < lines.length) {
    do {
      const line = lines[i++]!;
      for (const c of line) step(c);
      step(END);
    } while (state !== "START_RECORD" && i < lines.length);
    if (state !== "START_RECORD") {
      // The end of the input inside a record: what was read is its last field.
      if (fieldLen !== 0 || state === "IN_QUOTED_FIELD") save();
      if (fields.length > 0) rows.push(fields);
      return rows;
    }
    rows.push(fields);
    fields = [];
  }
  return rows;
}

// -- the processor --------------------------------------------------------------------

const WORDS: Record<string, string> = { tab: "\t", comma: ",", semicolon: ";", pipe: "|" };
const SNIFF_WINDOW = 8192;

function cell(value: string): string {
  return value.replaceAll("\r\n", " ").replaceAll("\n", " ").replaceAll("\r", " ").replaceAll("|", "\\|");
}

function table(header: string[], rows: string[][]): string {
  const lines = [`| ${header.map(cell).join(" | ")} |`, `| ${header.map(() => "---").join(" | ")} |`];
  for (const row of rows) lines.push(`| ${row.map(cell).join(" | ")} |`);
  return lines.join("\n");
}

export const csvProcessor: ProcessorFn = (data, options, { filename }) => {
  const source = filename || "table.csv";
  try {
    const [encoding, text] = guessDecode(data);
    if (isBlank(text)) {
      return makeArtifact({ meta: { kind: "table", note: "empty CSV", extra: { rows: 0, encoding, engine: "stdlib" } } });
    }
    let delimiter: string;
    const given = options["delimiter"];
    if (typeof given === "string" && given) {
      const word = given.trim().toLowerCase();
      delimiter = WORDS[word] ?? Array.from(given)[0]!;
    } else {
      delimiter =
        sniffDelimiter(new CodePoints(text).slice(0, SNIFF_WINDOW), ",;\t|") ?? (source.toLowerCase().endsWith(".tsv") ? "\t" : ",");
    }
    const records = readCsv(text, delimiter);
    const header = records[0]!;
    const dataRows = records.slice(1);
    const limit = typeof options["rows"] === "number" ? options["rows"] : 200;
    const extra: Record<string, unknown> = { rows: dataRows.length, cols: header.length, delimiter, encoding, engine: "stdlib" };
    if (dataRows.length > limit) extra["rows_truncated"] = true;
    const meta: Record<string, unknown> = { kind: "table", extra };
    if (options["summary"] === true) {
      meta["warnings"] = [
        "summary requested but this implementation has no summary (pandas, in Python); read the file with the service for one",
      ];
    }
    // Python's slice: a negative `rows` leaves out that many from the end.
    return makeArtifact({ text: table(header, dataRows.slice(0, limit)), meta });
  } catch (err) {
    return errorArtifact(source, "parse-error", `Failed to parse CSV: ${(err as Error).message}`);
  }
};
