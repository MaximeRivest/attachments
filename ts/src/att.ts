/**
 * `att()`: anything in, artifacts out (contract/reading.md).
 */

import { attachWarnings, errorArtifact, normalizeArtifact } from "./artifact.ts";
import { AttachmentsError, Artifacts } from "./artifacts.ts";
import { checkSettings, effective, type Effective, type Prefer, type Settings } from "./config.ts";
import { parseDslWritten } from "./dsl.ts";
import type { Options } from "./generated/options.ts";
import { allDeclared, declaredOptions, type OptionDecl, resolveOptions, writtenValue } from "./options.ts";
import { fromPrompt } from "./mentions.ts";
import { processFile } from "./route.ts";
import { unpackViaService } from "./service.ts";
import { isArchiveName } from "./sources/archives.ts";
import { resolve, resolveBytes, type Resolution, sources } from "./sources/index.ts";
import { needsOverview, overviewArtifact } from "./sources/overview.ts";
import { InvalidSourceOption, MAX_SCAN_ENTRIES_DEFAULT, treeOptions } from "./sources/tree.ts";
import { comparePoints } from "./text.ts";
import type {
  Artifact,
  ClaudeMessage,
  ErrorInfo,
  ImageItem,
  Lm15Message,
  OpenAIMessage,
  Part,
  Tier,
  TokenEstimate,
  WireArtifact,
} from "./types.ts";
import type { ChunkOptions, PresentOptions } from "./present.ts";
import { warn } from "./warn.ts";
import { MAX_DOWNLOAD_BYTES } from "./sources/download.ts";

/** What `att()` reads: text (a path, folder, pattern, address, with `[options]`), a `URL`, a `File` or `Blob`, or a list of them. */
export type Input = string | URL | Blob | Iterable<Input>;

/** Options of one call: the formats' options by their contract names, plus `prefer` and `signal`. */
export interface AttOptions extends Options {
  /** Where to read, for this call: `local`, `service`, `local-only`, `service-only`. */
  prefer?: Prefer | undefined;
  /** Stop reading: the promise rejects with the signal's reason. */
  signal?: AbortSignal | undefined;
}

/**
 * The promise `att()` returns. Await it for {@link Artifacts}, or call
 * their methods on it directly: each gives a promise of its result.
 *
 * @example
 * const messages = await att("report.pdf").claude("Summarize.");
 */
export interface PendingArtifacts extends Promise<Artifacts> {
  readonly text: Promise<string>;
  readonly images: Promise<ImageItem[]>;
  readonly errors: Promise<ErrorInfo[]>;
  readonly tokens: Promise<number>;
  toText(options?: { sources?: boolean | undefined }): Promise<string>;
  parts(options?: PresentOptions & { prompt?: string | undefined }): Promise<Part[]>;
  claude(prompt?: string, options?: PresentOptions): Promise<ClaudeMessage[]>;
  openai(prompt?: string, options?: PresentOptions): Promise<OpenAIMessage[]>;
  lm15(prompt?: string, options?: PresentOptions): Promise<Lm15Message>;
  chunk(options?: ChunkOptions): Promise<string[]>;
  estimateTokens(options?: { tier?: Tier | undefined }): Promise<TokenEstimate>;
  toWire(): Promise<WireArtifact[]>;
  /** Rejects with an {@link AttachmentsError} when any input failed; chain more calls after it. */
  throwIfErrors(): PendingArtifacts;
}

/** The methods and getters a pending result forwards (a test checks they are all of Artifacts'). @internal */
export const PENDING_METHODS = ["toText", "parts", "claude", "openai", "lm15", "chunk", "estimateTokens", "toWire"] as const;
export const PENDING_GETTERS = ["text", "images", "errors", "tokens"] as const;

function pending(promise: Promise<Artifacts>): PendingArtifacts {
  const p = promise as PendingArtifacts;
  for (const name of PENDING_GETTERS) {
    Object.defineProperty(p, name, { get: () => promise.then((a) => a[name]), enumerable: false });
  }
  for (const name of PENDING_METHODS) {
    Object.defineProperty(p, name, {
      value: (...args: unknown[]) => promise.then((a) => (a[name] as (...x: unknown[]) => unknown)(...args)),
      enumerable: false,
    });
  }
  Object.defineProperty(p, "throwIfErrors", { value: () => pending(promise.then((a) => a.throwIfErrors())), enumerable: false });
  return p;
}

// -- inputs ------------------------------------------------------------------------------

type Item = { kind: "text"; text: string; dsl: boolean } | { kind: "bytes"; name: string; blob: Blob } | { kind: "error"; artifact: Artifact };

/** Bytes that came without a name. */
export const UNNAMED = "file";

function describe(value: unknown): string {
  if (value === null) return "null";
  if (Array.isArray(value)) return "array";
  if (typeof value === "object") return (value as object).constructor?.name ?? "object";
  return typeof value;
}

function items(value: unknown, out: Item[] = []): Item[] {
  if (typeof value === "string") out.push({ kind: "text", text: value, dsl: true });
  else if (value instanceof URL) {
    out.push({ kind: "text", text: value.href, dsl: false });
  } else if (typeof Blob !== "undefined" && value instanceof Blob) {
    const raw = typeof (value as File).name === "string" ? (value as File).name : "";
    const name = raw.replaceAll("\\", "/").replace(/\/+$/u, "").split("/").at(-1) || UNNAMED;
    out.push({ kind: "bytes", name, blob: value });
  } else if (value instanceof Uint8Array || value instanceof ArrayBuffer) {
    out.push({
      kind: "error",
      artifact: errorArtifact(
        "<bytes>",
        "unpack-error",
        "att() takes paths, URLs and files, not bare bytes: without a name their format is a guess. Give them one: att(new File([bytes], \"report.pdf\"))",
      ),
    });
  } else if (value !== null && typeof value === "object" && Symbol.iterator in value) {
    for (const v of value as Iterable<unknown>) items(v, out);
  } else {
    out.push({
      kind: "error",
      artifact: errorArtifact(
        String(value).slice(0, 80),
        "unpack-error",
        `att() takes a path or URL (text or URL), a File, or a list of them; got ${describe(value)}.`,
      ),
    });
  }
  return out;
}

// -- options taken out before reading -----------------------------------------------------

const TREE_NAMES = new Set(["files", "tree", "ignore", "hidden", "glob", "recursive", "max_files", "max_size"]);

function sourceSchemaFor(input: string): readonly OptionDecl[] | null {
  const declared = allDeclared().sources;
  if (input.startsWith("https://github.com/") && input.split("/").length - 1 <= 4) return declared["github://"] ?? null;
  for (const [prefix, decls] of Object.entries(declared)) if (input.startsWith(prefix)) return decls;
  for (const prefix of sources.keys()) if (input.startsWith(prefix)) return null;
  if (input.startsWith("http://") || input.startsWith("https://")) {
    const path = input.split("?")[0]!.split("#")[0]!;
    return isArchiveName(path) ? (declared["file://"] ?? null) : null;
  }
  return declared["file://"] ?? null;
}

function takeTreeOptions(input: string, options: Record<string, unknown>): Record<string, unknown> {
  const schema = sourceSchemaFor(input);
  if (!schema) return {};
  const taken: Record<string, unknown> = {};
  for (const decl of schema) {
    if (!TREE_NAMES.has(decl.name)) continue;
    for (const key of Object.keys(options)) {
      if (key === decl.name || decl.aliases.includes(key)) {
        taken[key] = options[key];
        delete options[key];
      }
    }
  }
  return taken;
}

/** Python's `urllib.parse.quote(s, safe="")`. */
function pyQuote(text: string): string {
  return encodeURIComponent(text).replace(/[!'()*]/gu, (c) => `%${c.charCodeAt(0).toString(16).toUpperCase()}`);
}

function applySourceOptions(input: string, options: Record<string, unknown>): string {
  const schema = sourceSchemaFor(input);
  if (!schema) return input;
  const consumed: [string, unknown][] = [];
  for (const decl of schema) {
    const names = new Set([decl.name, ...decl.aliases, ...(decl.param ? [decl.param] : [])]);
    for (const key of Object.keys(options)) {
      if (names.has(key)) {
        consumed.push([decl.param ?? decl.name, writtenValue(decl, options[key])]);
        delete options[key];
      }
    }
  }
  for (const [key, value] of consumed) {
    if (!value) continue;
    input += `${input.includes("?") ? "&" : "?"}${key}=${pyQuote(String(value))}`;
  }
  return input;
}

// -- one input ----------------------------------------------------------------------------

const CONCURRENCY = 4;

async function inOrder<T, R>(list: readonly T[], run: (item: T) => Promise<R>): Promise<R[]> {
  const out = new Array<R>(list.length);
  let next = 0;
  const worker = async (): Promise<void> => {
    while (next < list.length) {
      const i = next++;
      out[i] = await run(list[i]!);
    }
  };
  await Promise.all(Array.from({ length: Math.min(CONCURRENCY, list.length) }, worker));
  return out;
}

const message = (err: unknown): string => (err instanceof Error ? err.message : String(err));

async function attOne(item: Exclude<Item, { kind: "error" }>, callOptions: Record<string, unknown>, settings: Effective, signal: AbortSignal | undefined): Promise<Artifact[]> {
  let input: string;
  let dslOptions: Record<string, unknown> = {};
  if (item.kind === "text" && item.dsl) [input, dslOptions] = parseDslWritten(item.text);
  else input = item.kind === "text" ? item.text : item.name;
  const merged: Record<string, unknown> = { ...dslOptions, ...callOptions };

  const treeRaw = takeTreeOptions(input, merged);
  const tree = resolveOptions(declaredOptions("file://").filter((d) => TREE_NAMES.has(d.name)), treeRaw, "folders");
  for (const w of tree.warnings) warn(w, "OptionWarning");
  let treeWarnings = tree.warnings;
  input = applySourceOptions(input, merged);

  let resolution: Resolution;
  try {
    const [opts, fromWarnings] = treeOptions(tree.options);
    if (item.kind === "bytes") {
      const data = new Uint8Array(await item.blob.arrayBuffer());
      resolution = await resolveBytes(input, data, opts, fromWarnings);
    } else {
      resolution = await resolve(input, opts, fromWarnings, {
        blockPrivateUrls: settings.blockPrivateUrls,
        maxDownload: MAX_DOWNLOAD_BYTES,
        signal,
      });
    }
  } catch (err) {
    signal?.throwIfAborted();
    if (err instanceof InvalidSourceOption) return [errorArtifact(input, "invalid-option", err.message)];
    if (item.kind === "text" && settings.serviceConfigured && settings.prefer !== "local-only") {
      try {
        const files = await unpackViaService(settings, input, signal);
        resolution = { files, reports: [] };
      } catch (serviceErr) {
        signal?.throwIfAborted();
        return [errorArtifact(input, "unpack-error", `unpack failed: ${message(err)}; service: ${message(serviceErr)}`)];
      }
    } else return [errorArtifact(input, "unpack-error", `unpack failed: ${message(err)}`)];
  }

  const out: Artifact[] = [];
  for (const report of resolution.reports) {
    report.warnings.unshift(...treeWarnings);
    if (needsOverview(report)) out.push(overviewArtifact(report, MAX_SCAN_ENTRIES_DEFAULT));
  }
  if (Object.keys(treeRaw).length > 0 && resolution.reports.length === 0) {
    const names = Object.keys(treeRaw).sort(comparePoints).join(", ");
    treeWarnings = [...treeWarnings, `Folder options (${names}) apply to folders, patterns, repositories and archives; ignored for a single file.`];
  } else if (resolution.reports.length > 0) treeWarnings = [];

  const artifacts = await inOrder(resolution.files, async (file) => {
    signal?.throwIfAborted();
    const artifact = normalizeArtifact(
      await processFile({ filename: file.name, data: file.data, options: merged, settings, url: file.url, signal }),
      file.name,
    );
    if (file.url) artifact.meta.source = file.url;
    return attachWarnings(artifact, [...(file.warnings ?? []), ...treeWarnings]);
  });
  return [...out, ...artifacts];
}

async function run(input: unknown, options: AttOptions, base: Settings): Promise<Artifacts> {
  const { prefer, signal, ...formatOptions } = options;
  const settings = effective(prefer !== undefined ? { ...base, prefer } : base);
  signal?.throwIfAborted();
  const results = await inOrder(items(input), (item) =>
    item.kind === "error" ? Promise.resolve([item.artifact]) : attOne(item, { ...formatOptions }, settings, signal),
  );
  return Artifacts.from(results.flat());
}

// -- the att function ----------------------------------------------------------------------

/** `att`: call it, or use its helpers. */
export interface Att {
  /**
   * Read anything into artifacts: a path, folder, pattern, web address,
   * `github://owner/repo`, a `File`, or a list of them, each with
   * optional `[options]`.
   */
  (input: Input, options?: AttOptions): PendingArtifacts;
  /** An `att` with settings of its own (a key per user on a server). */
  with(settings: Settings): Att;
  /** The files (and with `urls`, web pages) a prompt mentions, inside `root` folders only. */
  fromPrompt(prompt: string, options?: FromPromptOptions): PendingArtifacts;
  /** The options one format (`".pdf"`) or source (`"github://"`) declares. */
  options(key: string): readonly OptionDecl[];
  /** Every format's and source's options. */
  options(): OptionCatalog;
  /** A one-screen overview of the API. */
  help(): void;
}

/** Every declared option: `att.options()`. */
export interface OptionCatalog {
  version: number;
  processors: Record<string, readonly OptionDecl[]>;
  sources: Record<string, readonly OptionDecl[]>;
}

export interface FromPromptOptions extends AttOptions {
  /** Folders mentions are looked up in and confined to (default: the current folder). */
  root?: string | readonly string[] | undefined;
  /** Also fetch `http(s)://` addresses in the prompt (off: the prompt's author would choose what this machine fetches). */
  urls?: boolean | undefined;
}


const HELP = `attachments-dev — any file, folder or web page into what a model reads

  const a = await att("report.pdf[pages: 1-4]")   // paths, folders, globs, URLs, github://o/r, File
  await att("scan.pdf", { pages: "1-4", ocr: true }) // options as in the string, same names
  await att(["notes/", "https://example.com/post"]) // several inputs, in order

  a.text  \`\${a}\`  a.images  a.errors  a.tokens       // the prompt text, pictures, failures, tokens
  a.claude("Q")  a.openai("Q")  a.lm15("Q")           // messages for each SDK
  a.parts()  a.chunk({ maxChars: 4000 })              // neutral parts, chunks for retrieval
  a.throwIfErrors()  a.toWire()  Artifacts.fromWire(json)

  await att("report.pdf").claude("Summarize.")        // any method on the pending result
  configure({ apiKey })  /  att.with({ apiKey })      // the service, for formats read there
  att.options(".pdf")                                 // what a format accepts
  att.fromPrompt("Compare \`a.csv\` with b.md", { root: "data" })
`;

function makeAtt(base: Settings): Att {
  checkSettings(base, "att.with");
  const att = ((input: Input, options: AttOptions = {}) => pending(run(input, options, base))) as Att;
  att.with = (settings) => makeAtt({ ...base, ...settings });
  att.fromPrompt = (prompt, options = {}) => pending(fromPrompt(att, prompt, options));
  att.options = ((key?: string) => (key === undefined ? { version: 1, ...allDeclared() } : declaredOptions(key))) as Att["options"];
  att.help = () => console.log(HELP);
  return att;
}

/**
 * Read anything into artifacts.
 *
 * @example
 * const a = await att("report.pdf[pages: 1-4]");
 * const messages = await att("report.pdf").claude("Summarize.");
 */
export const att: Att = makeAtt({});

export { AttachmentsError };
