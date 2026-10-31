/**
 * Artifacts into what a model reads (contract/presenting.md): text,
 * parts, Claude/OpenAI/lm15 messages, chunks, token estimates.
 *
 * @internal
 */

import { decodeLoose, encode } from "./base64.ts";
import { imageSize } from "./imagesize.ts";
import { CLAUDE, checkRequest, OPENAI } from "./limits.ts";
import { CodePoints, cpLength, isBlank, roundHalfEven, strip } from "./text.ts";
import type {
  Artifact,
  ClaudeBlock,
  ClaudeImageType,
  ClaudeMessage,
  ImageItem,
  Lm15Message,
  Lm15Part,
  OpenAIMessage,
  OpenAIPart,
  Part,
  Tier,
  TokenEstimate,
} from "./types.ts";
import { warn } from "./warn.ts";

/** Arguments every presenter takes. */
export interface PresentOptions {
  /** Show file names: `## <source>` headers, names in `[image: <name>]` (default true). */
  sources?: boolean | undefined;
  /** Put each page's pictures right after its text (default true). */
  interleave?: boolean | undefined;
}

type ImagePart = Extract<Part, { type: "image" }>;

const source = (a: Artifact): string => a.meta?.source || "(unknown)";

function imageData(image: ImageItem): string | null {
  const raw = (image as { bytes?: unknown }).bytes;
  if (raw instanceof Uint8Array) return encode(raw);
  const b64 = (image as { bytes_b64?: unknown }).bytes_b64;
  return typeof b64 === "string" && b64 ? b64 : null;
}

function imagePart(image: ImageItem): ImagePart | null {
  const data = imageData(image);
  if (data === null) return null;
  return { type: "image", media_type: image.mimetype || "application/octet-stream", data };
}

function shown(artifacts: readonly Artifact[], sources: boolean): Artifact[] {
  return sources ? [...artifacts] : artifacts.filter((a) => a.meta?.kind !== "directory");
}

function warnNamedLabels(artifacts: readonly Artifact[]): void {
  const named = artifacts
    .filter((a) => (a.images?.length ?? 0) > 0)
    .filter((a) => {
      const template = (a.meta?.extra as { watermark?: unknown } | undefined)?.watermark;
      return typeof template === "string" && template.includes("{name}");
    })
    .map(source);
  if (named.length > 0) {
    warn(
      `sources=False, but the pictures of ${named.join(", ")} carry their file name (watermark: name); use watermark: page to keep names out`,
      "AttachmentsWarning",
    );
  }
}

/** The assembled prompt text. */
export function renderText(artifacts: readonly Artifact[], { sources = true }: { sources?: boolean | undefined } = {}): string {
  const blocks: string[] = [];
  for (const artifact of shown(artifacts, sources)) {
    const text = strip(artifact.text || "");
    let lines: string[];
    if (text) lines = [text];
    else if ((artifact.images?.length ?? 0) > 0) {
      lines = artifact.images.map((img) => (sources ? `[image: ${img.name || "image"}]` : "[image]"));
    } else continue;
    if (sources) lines.unshift(`## ${source(artifact)}`);
    blocks.push(lines.join("\n"));
  }
  return blocks.join("\n\n");
}

const isInt = (v: unknown): v is number => typeof v === "number" && Number.isInteger(v);

/** The text and image pieces of one artifact, without its name. */
function pieces(artifact: Artifact): Part[] {
  const text = new CodePoints(artifact.text || "");
  let images: { page: number | null; part: ImagePart }[] = [];
  for (const image of artifact.images ?? []) {
    const part = imagePart(image);
    if (part !== null) images.push({ page: isInt(image.page) ? image.page : null, part });
  }
  const out: Part[] = [];
  let cursor = 0;
  const flush = (upto: number): void => {
    if (upto > cursor) {
      const piece = strip(text.slice(cursor, upto));
      if (piece) out.push({ type: "text", text: piece });
      cursor = upto;
    }
  };
  const segments = (artifact.meta?.segments ?? [])
    .filter((s) => isInt(s.page) && isInt(s.start) && isInt(s.end))
    .map((s) => [s.start, s.end, s.page!] as const)
    .sort((x, y) => x[0] - y[0] || x[1] - y[1] || x[2] - y[2]);
  if (segments.length > 0 && images.some((i) => i.page !== null)) {
    const take = (keep: (page: number | null) => boolean): ImagePart[] => {
      const taken = images.filter((i) => keep(i.page)).map((i) => i.part);
      images = images.filter((i) => !keep(i.page));
      return taken;
    };
    for (const [start, end, page] of segments) {
      const before = take((p) => p !== null && p < page);
      if (before.length > 0) {
        flush(start);
        out.push(...before);
      }
      const here = take((p) => p === page);
      if (here.length > 0) {
        flush(end);
        out.push(...here);
      }
    }
  }
  flush(text.length);
  out.push(...images.map((i) => i.part));
  return out;
}

/** Provider-neutral parts: each page's text followed by that page's pictures. */
export function toParts(
  artifacts: readonly Artifact[],
  { sources = true, interleave = true, prompt }: PresentOptions & { prompt?: string | null | undefined } = {},
): Part[] {
  const parts: Part[] = [];
  const add = (part: Part): void => {
    const last = parts.at(-1);
    if (part.type === "text" && last?.type === "text") {
      parts[parts.length - 1] = { type: "text", text: `${last.text}\n\n${part.text}` };
    } else parts.push(part);
  };
  const list = shown(artifacts, sources);
  if (!sources) warnNamedLabels(list);
  if (interleave) {
    for (const artifact of list) {
      const p = pieces(artifact);
      if (p.length === 0) continue;
      if (sources) {
        const header = `## ${source(artifact)}`;
        const first = p[0]!;
        if (first.type === "text") p[0] = { type: "text", text: `${header}\n${first.text}` };
        else p.unshift({ type: "text", text: header });
      }
      p.forEach(add);
    }
  } else {
    const text = renderText(list, { sources });
    if (text) add({ type: "text", text });
    for (const artifact of list) {
      for (const image of artifact.images ?? []) {
        const part = imagePart(image);
        if (part !== null) parts.push(part);
      }
    }
  }
  if (prompt) parts.push({ type: "text", text: prompt });
  return parts;
}

/** Claude Messages API `messages`: one user message. */
export function toClaudeMessages(artifacts: readonly Artifact[], prompt?: string | null, options: PresentOptions = {}): ClaudeMessage[] {
  const parts = toParts(artifacts, { ...options, prompt });
  checkRequest(parts, CLAUDE);
  const content: ClaudeBlock[] = parts.map((p) =>
    p.type === "text"
      ? { type: "text", text: p.text }
      : { type: "image", source: { type: "base64", media_type: p.media_type as ClaudeImageType, data: p.data } },
  );
  return [{ role: "user", content }];
}

/** OpenAI Chat Completions `messages`: one user message. */
export function toOpenAIMessages(artifacts: readonly Artifact[], prompt?: string | null, options: PresentOptions = {}): OpenAIMessage[] {
  const parts = toParts(artifacts, { ...options, prompt });
  checkRequest(parts, OPENAI);
  const content: OpenAIPart[] = parts.map((p) =>
    p.type === "text" ? { type: "text", text: p.text } : { type: "image_url", image_url: { url: `data:${p.media_type};base64,${p.data}` } },
  );
  return [{ role: "user", content }];
}

/** One lm15 `Message` from the user. Throws when there is nothing to send. */
export function toLm15Message(artifacts: readonly Artifact[], prompt?: string | null, options: PresentOptions = {}): Lm15Message {
  const parts = toParts(artifacts, { ...options, prompt });
  if (parts.length === 0) {
    throw new RangeError("nothing to send: no text, no pictures and no prompt (failed files are listed in a.errors)");
  }
  const out: Lm15Part[] = parts.map((p) =>
    Object.freeze(p.type === "text" ? { type: "text" as const, text: p.text } : { type: "image" as const, mediaType: p.media_type, data: p.data }),
  );
  return Object.freeze({ role: "user" as const, parts: Object.freeze(out) });
}

// -- chunks ------------------------------------------------------------------

export interface ChunkOptions {
  /** Most characters (code points) in a chunk's body (default 8,000). */
  maxChars?: number | undefined;
  /** The cap in approximate tokens: `maxTokens × 4` characters; the smaller cap wins. */
  maxTokens?: number | undefined;
  /** Characters repeated between consecutive windows (default 200). */
  overlap?: number | undefined;
  /** Start each chunk with `## <source>` (default true). */
  sources?: boolean | undefined;
}

function findCut(text: CodePoints, lo: number, hi: number): number | null {
  for (const sep of ["\n\n", "\n", " "]) {
    const at = text.rfind(sep, lo, hi);
    if (at !== -1) return at + cpLength(sep);
  }
  return null;
}

function splitWindow(text: CodePoints, maxChars: number, overlap: number): string[] {
  const n = text.length;
  if (n <= maxChars) return n > 0 ? [text.text] : [];
  const out: string[] = [];
  let start = 0;
  for (;;) {
    let end = Math.min(start + maxChars, n);
    if (end < n) {
      const lo = Math.max(start, end - Math.max(1, Math.floor(maxChars / 5)));
      const cut = findCut(text, lo, end);
      if (cut !== null && cut > start) end = cut;
    }
    out.push(text.slice(start, end));
    if (end >= n) break;
    start = Math.max(end - overlap, start + 1);
  }
  return out;
}

function packSegments(text: CodePoints, segments: readonly { start?: unknown; end?: unknown }[], maxChars: number, overlap: number): string[] {
  const n = text.length;
  const spans: [number, number][] = [];
  for (const s of segments) {
    const start0 = Math.trunc(Number(s.start ?? 0));
    const end0 = Math.trunc(Number(s.end ?? 0));
    if (!Number.isFinite(start0) || !Number.isFinite(end0)) continue;
    const start = Math.max(0, Math.min(n, start0));
    const end = Math.max(start, Math.min(n, end0));
    if (end > start) spans.push([start, end]);
  }
  spans.sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  const bodies: string[] = [];
  let i = 0;
  while (i < spans.length) {
    const start = spans[i]![0];
    let end = spans[i]![1];
    if (end - start > maxChars) {
      bodies.push(...splitWindow(new CodePoints(text.slice(start, end)), maxChars, overlap));
      i++;
      continue;
    }
    let j = i + 1;
    while (j < spans.length && Math.max(end, spans[j]![1]) - start <= maxChars) {
      end = Math.max(end, spans[j]![1]);
      j++;
    }
    bodies.push(text.slice(start, end));
    i = j;
  }
  return bodies;
}

/** Chunks for retrieval: whole pages packed together, long text cut at paragraph, line or word. */
export function chunk(artifacts: readonly Artifact[], { maxChars, maxTokens, overlap = 200, sources = true }: ChunkOptions = {}): string[] {
  const caps: number[] = [];
  if (maxChars != null) caps.push(maxChars);
  if (maxTokens != null) caps.push(maxTokens * 4);
  const cap = caps.length > 0 ? Math.min(...caps) : 8000;
  if (!(cap >= 1)) throw new RangeError(`maxChars must be >= 1, got ${cap}`);
  const lap = Math.max(0, Math.min(Math.trunc(overlap), cap - 1));
  const out: string[] = [];
  for (const artifact of shown(artifacts, sources)) {
    const raw = artifact.text || "";
    if (isBlank(raw)) continue;
    const text = new CodePoints(raw);
    const segments = artifact.meta?.segments ?? [];
    const bodies = segments.length > 0 ? packSegments(text, segments, cap, lap) : splitWindow(text, cap, lap);
    if (sources) {
      const header = `## ${source(artifact)}`;
      for (const body of bodies) out.push(`${header}\n${body}`);
    } else out.push(...bodies);
  }
  return out;
}

// -- token estimates ------------------------------------------------------------

const TIERS: Record<Tier, readonly [edge: number, budget: number]> = { high: [2576, 4784], standard: [1568, 1568] };
const PATCH = 28;

const ceilDiv = (a: number, b: number): number => Math.ceil(a / b);
const patches = (w: number, h: number): number => ceilDiv(w, PATCH) * ceilDiv(h, PATCH);

function claudeSize(width: number, height: number, edge: number, budget: number): [number, number] {
  const fits = (w: number, h: number): boolean =>
    ceilDiv(w, PATCH) * PATCH <= edge && ceilDiv(h, PATCH) * PATCH <= edge && patches(w, h) <= budget;
  if (fits(width, height)) return [width, height];
  if (height > width) {
    const [h, w] = claudeSize(height, width, edge, budget);
    return [w, h];
  }
  const aspect = width / height;
  let lo = 1;
  let hi = width;
  while (lo + 1 < hi) {
    const mid = Math.floor((lo + hi) / 2);
    if (fits(mid, Math.max(roundHalfEven(mid / aspect), 1))) lo = mid;
    else hi = mid;
  }
  return [lo, Math.max(roundHalfEven(lo / aspect), 1)];
}

function tierOf(tier: string): readonly [number, number] {
  const found = (TIERS as Record<string, readonly [number, number]>)[tier];
  if (found === undefined) throw new RangeError(`tier must be one of ["high", "standard"], got ${JSON.stringify(tier)}`);
  return found;
}

/** Tokens Claude counts for one picture of `width` × `height` pixels. */
export function imageTokens(width: number, height: number, { tier = "high" }: { tier?: Tier | undefined } = {}): number {
  if (width <= 0 || height <= 0) return 0;
  const [edge, budget] = tierOf(tier);
  return patches(...claudeSize(width, height, edge, budget));
}

function imageItemTokens(image: ImageItem, tier: Tier): number {
  let raw: Uint8Array | null = null;
  const bytes = (image as { bytes?: unknown }).bytes;
  if (bytes instanceof Uint8Array) raw = bytes;
  else {
    const b64 = (image as { bytes_b64?: unknown }).bytes_b64;
    if (typeof b64 !== "string" || !b64) return 0;
    raw = decodeLoose(b64);
    if (raw === null) return 0;
  }
  const size = imageSize(raw);
  if (size === null) return tierOf(tier)[1];
  return imageTokens(size[0], size[1], { tier });
}

/** A rough token cost: text is characters ÷ 4; pictures as Claude counts them. */
export function estimateTokens(artifacts: readonly Artifact[], { tier = "high" }: { tier?: Tier | undefined } = {}): TokenEstimate {
  tierOf(tier);
  let chars = 0;
  for (const a of artifacts) chars += cpLength(a.text || "");
  const text = Math.ceil(chars / 4);
  let images = 0;
  for (const a of artifacts) for (const image of a.images ?? []) images += imageItemTokens(image, tier);
  return { text, images, total: text + images };
}
