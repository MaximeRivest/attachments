/**
 * Jupyter notebooks (contract/processors.md, "Jupyter notebooks").
 *
 * @internal
 */

import { decodeLoose } from "../base64.ts";
import { errorArtifact, makeArtifact } from "../artifact.ts";
import type { ProcessorFn } from "../processors.ts";
import { cpLength, CodePoints, strip } from "../text.ts";
import type { ImageItem, Segment } from "../types.ts";
import { isDict, loads, plain, type PyJson, pyStr, truthy } from "./pyjson.ts";

const LIMIT = 2000;
const MARKER = "… (truncated)";

/** Python's `d.get(key)` on a value that must be a dict (a crash otherwise, as in Python). */
function get(d: PyJson | undefined, key: string): PyJson | undefined {
  if (!isDict(d)) throw new TypeError(`'${Array.isArray(d) ? "list" : typeof d}' object has no attribute 'get'`);
  return d[key];
}

/** Python's `for x in v`: a list's items, a dict's keys, a string's characters; a crash otherwise. */
function iterate(v: PyJson): PyJson[] {
  if (Array.isArray(v)) return v;
  if (typeof v === "string") return Array.from(v);
  if (isDict(v)) return Object.keys(v);
  throw new TypeError("object is not iterable");
}

/** `a or b`: `a` when Python finds it true. */
const or = (a: PyJson | undefined, b: PyJson): PyJson => (truthy(a) ? (a as PyJson) : b);

function joinSource(source: PyJson | undefined): string {
  if (Array.isArray(source)) return source.map(pyStr).join("");
  return source === undefined || source === null ? "" : pyStr(source);
}

/** Python's `str.rstrip()` (white space). */
function rstrip(text: string): string {
  const s = strip(`x${text}`);
  return s.slice(1);
}

function truncate(text: string): string {
  const points = new CodePoints(text);
  if (points.length <= LIMIT) return text;
  return `${rstrip(points.slice(0, LIMIT))}\n${MARKER}`;
}

const stripNewlines = (s: string): string => s.replace(/^\n+|\n+$/gu, "");

function outputTexts(cell: { [key: string]: PyJson }): string[] {
  const texts: string[] = [];
  for (const out of iterate(or(get(cell, "outputs"), []))) {
    if (!isDict(out)) continue;
    const type = out["output_type"];
    let text: string;
    if (type === "stream") text = joinSource(out["text"]);
    else if (type === "execute_result" || type === "display_data") text = joinSource(get(or(out["data"], {}), "text/plain"));
    else if (type === "error") text = iterate(or(out["traceback"], [])).map(pyStr).join("\n");
    else text = "";
    text = stripNewlines(text);
    if (text) texts.push(truncate(text));
  }
  return texts;
}

function outputImages(cell: { [key: string]: PyJson }, cellNo: number, stem: string): ImageItem[] {
  const images: ImageItem[] = [];
  for (const out of iterate(or(get(cell, "outputs"), []))) {
    if (!isDict(out)) continue;
    const b64 = get(or(out["data"], {}), "image/png");
    if (!truthy(b64)) continue;
    const text = joinSource(b64);
    // Python's b64decode of text: ASCII only, other characters dropped.
    const bytes = /^[\x00-\x7f]*$/u.test(text) ? decodeLoose(text) : null;
    if (bytes === null) continue;
    const suffix = images.length === 0 ? "" : `-${images.length + 1}`;
    images.push({ name: `${stem}-cell-${cellNo}-output${suffix}.png`, mimetype: "image/png", bytes });
  }
  return images;
}

type Kind = "code" | "markdown" | "raw";

function renderCell(cell: { [key: string]: PyJson }, language: string, outputs: boolean): [Kind, string] {
  const type = pyStr(or(get(cell, "cell_type"), "raw"));
  const source = joinSource(get(cell, "source"));
  if (type === "code") {
    const parts = [`\`\`\`${language}\n${source}\n\`\`\``];
    if (outputs) for (const t of outputTexts(cell)) parts.push(`\`\`\`output\n${t}\n\`\`\``);
    return ["code", parts.join("\n\n")];
  }
  if (type === "markdown") return ["markdown", source];
  return ["raw", source];
}

export const ipynbProcessor: ProcessorFn = (data, options, { filename }) => {
  const source = filename || "file.ipynb";
  let stem = source.slice(source.lastIndexOf("/") + 1);
  if (stem.toLowerCase().endsWith(".ipynb")) stem = stem.slice(0, -6);
  let nb: PyJson;
  try {
    nb = loads(new TextDecoder("utf-8", { ignoreBOM: true }).decode(data));
  } catch (err) {
    return errorArtifact(source, "parse-error", `Failed to parse notebook: ${(err as Error).message}`);
  }
  if (!isDict(nb)) return errorArtifact(source, "parse-error", "Failed to parse notebook: not a JSON object");
  const cells = nb["cells"];
  if (cells === undefined || cells === null) {
    if ("worksheets" in nb) {
      return errorArtifact(
        source,
        "parse-error",
        "Notebook uses the legacy nbformat 3 layout ('worksheets'); only nbformat 4 is supported. Upgrade it with: jupyter nbconvert --to notebook file.ipynb",
      );
    }
    return errorArtifact(source, "parse-error", "Failed to parse notebook: missing 'cells' key");
  }
  if (!Array.isArray(cells)) return errorArtifact(source, "parse-error", "Failed to parse notebook: 'cells' is not a list");
  const metadata = or(nb["metadata"], {});
  let languageValue = get(or(get(metadata, "language_info"), {}), "name");
  if (!truthy(languageValue)) languageValue = get(or(get(metadata, "kernelspec"), {}), "language");
  if (!truthy(languageValue)) languageValue = "python";
  const language = pyStr(languageValue!);
  const outputs = options["outputs"] === true;
  const parts: string[] = [];
  const segments: Segment[] = [];
  const images: ImageItem[] = [];
  const counts: Record<Kind, number> = { code: 0, markdown: 0, raw: 0 };
  let offset = 0;
  cells.forEach((raw, index) => {
    const cell = isDict(raw) ? raw : {};
    const [kind, text] = renderCell(cell, language, outputs);
    counts[kind]++;
    if (outputs && kind === "code") images.push(...outputImages(cell, index + 1, stem));
    if (parts.length > 0) offset += 2;
    const length = cpLength(text);
    segments.push({ kind: "section", label: `cell ${index + 1} (${kind})`, start: offset, end: offset + length });
    parts.push(text);
    offset += length;
  });
  const extra = { cell_counts: counts, language: plain(languageValue!), nbformat: "nbformat" in nb ? plain(nb["nbformat"]!) : 4 };
  return makeArtifact({ text: parts.join("\n\n"), images, meta: { kind: "notebook", extra, ...(segments.length ? { segments } : {}) } });
};
