/**
 * Processors: what reads each format, and which one a file goes to
 * (contract/reading.md, "Routing a file").
 *
 * @internal
 */

import { errorArtifact, makeArtifact, missingDepArtifact } from "./artifact.ts";
import { READING } from "./generated/reading.ts";
import { PROCESSOR_OPTIONS } from "./generated/schema.ts";
import { cpLength } from "./text.ts";
import { guessDecode, latin1 } from "./decode.ts";
import type { Artifact } from "./types.ts";
import { zipNames } from "./sources/archives.ts";
import type { OptionDecl, OptionValue } from "./options.ts";
import { csvProcessor } from "./readers/csv.ts";
import { ipynbProcessor } from "./readers/ipynb.ts";
import { svgProcessor } from "./readers/svg.ts";

/** What a processor gets besides the file and its options. */
export interface ProcessorContext {
  /** The file's name (its path inside a folder or archive). */
  filename: string;
  /** The standard processing of this format, for named processors that refine it. */
  base: (data?: Uint8Array, options?: Record<string, unknown>) => Promise<Artifact>;
  signal?: AbortSignal | undefined;
}

/** A processor: the file's bytes and its resolved options in, one artifact out. */
export type ProcessorFn = (
  data: Uint8Array,
  options: Record<string, OptionValue>,
  context: ProcessorContext,
) => Artifact | Promise<Artifact>;

export interface NamedProcessor {
  name: string;
  fn: ProcessorFn;
  /** Its own options, on top of the standard processor's. */
  options: readonly OptionDecl[];
  detect: ((data: Uint8Array, filename: string) => boolean | Promise<boolean>) | null;
}

/** Extension (`.pdf`) or `__text__` → the standard processor. */
export const processors = new Map<string, ProcessorFn>();
/** Extension → name → named processor, in registration order. */
export const namedProcessors = new Map<string, Map<string, NamedProcessor>>();
export const STANDARD = "default";

export function normalizeKey(key: string): string {
  let k = key.trim();
  if (k.startsWith("__")) return k;
  if (!k.startsWith(".")) k = `.${k}`;
  return k.toLowerCase();
}

// -- the text processor --------------------------------------------------------------

export const textProcessor: ProcessorFn = (data, _options, { filename }) => {
  const [encoding, text] = guessDecode(data);
  return makeArtifact({ text, meta: { kind: "text", extra: { encoding, chars: cpLength(text), filename } } });
};

processors.set("__text__", textProcessor);
for (const ext of READING.text_extensions) processors.set(ext, textProcessor);
for (const ext of [".csv", ".tsv"]) processors.set(ext, csvProcessor);
processors.set(".ipynb", ipynbProcessor);
for (const ext of [".svg", ".svgz"]) processors.set(ext, svgProcessor);

/** Processors that only say a reader is missing. */
export const PLACEHOLDERS = new WeakSet<ProcessorFn>();

// Formats the contract knows that TypeScript cannot read yet: a missing
// dependency, so the service reads them when one is configured.
const FEATURES: Record<string, string> = {
  ".pdf": "pdf", ".docx": "docx", ".pptx": "pptx", ".xlsx": "xlsx", ".xls": "xls", ".csv": "csv", ".tsv": "csv",
  ".html": "html", ".htm": "html", ".svg": "svg", ".svgz": "svg", ".ipynb": "ipynb", ".heic": "heic", ".heif": "heic",
  ".doc": "libreoffice", ".odt": "libreoffice", ".ppt": "libreoffice", ".odp": "libreoffice", ".ods": "libreoffice",
};
const AUDIO = [".mp3", ".wav", ".m4a", ".flac", ".ogg", ".opus"];
const IMAGES = [".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff", ".tif"];
for (const key of Object.keys(PROCESSOR_OPTIONS)) {
  if (processors.has(key)) continue;
  const feature = FEATURES[key] ?? (AUDIO.includes(key) ? "audio" : IMAGES.includes(key) ? "image" : key.slice(1));
  const placeholder: ProcessorFn = (_data, _options, { filename }) => missingDepArtifact(filename, feature);
  PLACEHOLDERS.add(placeholder);
  processors.set(key, placeholder);
}

// -- sniffing --------------------------------------------------------------------------

const startsWith = (d: Uint8Array, ascii: string, at = 0): boolean => {
  if (d.length < at + ascii.length) return false;
  for (let i = 0; i < ascii.length; i++) if (d[at + i] !== ascii.charCodeAt(i)) return false;
  return true;
};

const WHITE = new Set([0x20, 0x09, 0x0a, 0x0b, 0x0c, 0x0d]);

/** An extension from the content's first bytes, or `null`. */
export function detectExtension(data: Uint8Array): string | null {
  if (startsWith(data, "%PDF-")) return ".pdf";
  if (startsWith(data, "\x89PNG")) return ".png";
  if (data.length >= 3 && data[0] === 0xff && data[1] === 0xd8 && data[2] === 0xff) return ".jpg";
  if (startsWith(data, "GIF87a") || startsWith(data, "GIF89a")) return ".gif";
  if (startsWith(data, "RIFF") && startsWith(data, "WEBP", 8)) return ".webp";
  if (startsWith(data, "BM") && data.length >= 26) {
    const declared = (data[2]! | (data[3]! << 8) | (data[4]! << 16)) + data[5]! * 2 ** 24;
    if (declared === 0 || declared === data.length) return ".bmp";
  }
  if (startsWith(data, "PK\x03\x04")) {
    const names = zipNames(data);
    if (names === null || !names.includes("[Content_Types].xml")) return null;
    for (const [prefix, ext] of [["word/", ".docx"], ["xl/", ".xlsx"], ["ppt/", ".pptx"]] as const) {
      if (names.some((n) => n.startsWith(prefix))) return ext;
    }
    return null;
  }
  let i = data[0] === 0xef && data[1] === 0xbb && data[2] === 0xbf ? 3 : 0;
  while (i < data.length && WHITE.has(data[i]!)) i++;
  const head = latin1(data.subarray(i, i + 256)).toLowerCase();
  return head.startsWith("<!doctype html") || head.startsWith("<html") ? ".html" : null;
}

const TEXT_BYTES = new Set([7, 8, 9, 10, 12, 13, 27]);

/** Empty, or no NUL and fewer than 5% of bytes outside the printable set. */
export function isTextBytes(data: Uint8Array): boolean {
  if (data.length === 0) return true;
  let bad = 0;
  for (const b of data) {
    if (b === 0) return false;
    if (b < 0x20 && !TEXT_BYTES.has(b)) bad++;
  }
  return bad / data.length < 0.05;
}

function extension(filename: string): string {
  // Python's os.path.splitext: the last dot not at the start of the name.
  const base = filename.slice(filename.lastIndexOf("/") + 1);
  const dot = base.lastIndexOf(".");
  if (dot <= 0 || /^\.+$/u.test(base.slice(0, dot + 1))) return "";
  return base.slice(dot).toLowerCase();
}

/** `[processor, key]` for a file, or `[null, extension]`. */
export function routeProcessor(filename: string, data: Uint8Array): [ProcessorFn | null, string] {
  const ext = extension(filename);
  const byName = processors.get(ext);
  if (byName) return [byName, ext];
  const sniffed = detectExtension(data);
  if (sniffed !== null && processors.has(sniffed)) return [processors.get(sniffed)!, sniffed];
  if (isTextBytes(data) && processors.has("__text__")) return [processors.get("__text__")!, "__text__"];
  return [null, ext];
}

export { extension, errorArtifact, guessDecode };
