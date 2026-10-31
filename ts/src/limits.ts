/**
 * Provider request limits (contract/presenting.md, "Request limits"),
 * checked when `.claude()` / `.openai()` build a request, so a request that
 * would be rejected says why, with the fix, before it is sent. A warning,
 * not an error: a gateway may accept other limits.
 *
 * @internal
 */

import { decodeLoose } from "./base64.ts";
import { imageSize } from "./imagesize.ts";
import { fixed1, jsonSize } from "./text.ts";
import type { Part } from "./types.ts";
import { warn } from "./warn.ts";

export interface Limits {
  provider: string;
  requestBytes: number;
  requestNote: string;
  images: number;
  imagesNote: string;
  imageB64Bytes?: number;
  imageNote?: string;
  maxSide?: number;
  manyImages?: number;
  manySide?: number;
  mediaTypes: readonly string[];
}

const TYPES = ["image/jpeg", "image/png", "image/gif", "image/webp"] as const;

export const CLAUDE: Limits = {
  provider: "Claude",
  requestBytes: 32_000_000,
  requestNote: "Bedrock: 20 MB, Google Cloud: 30 MB",
  images: 100,
  imagesNote: "100 for models with a 200k-token context, 600 for others",
  imageB64Bytes: 10_000_000,
  imageNote: "5 MB on Bedrock and Google Cloud",
  maxSide: 8000,
  manyImages: 20,
  manySide: 2000,
  mediaTypes: TYPES,
};

export const OPENAI: Limits = {
  provider: "OpenAI",
  requestBytes: 512_000_000,
  requestNote: "",
  images: 1500,
  imagesNote: "",
  mediaTypes: TYPES,
};

/** Base64 characters decoded to find a picture's size (64 KiB). */
const HEADER_B64 = 87_384;

const mb = (n: number): string => `${fixed1(n / 1e6)} MB`;

function size(data: string): [number, number] | null {
  const head = decodeLoose(data.slice(0, HEADER_B64));
  if (head === null) return null;
  const found = imageSize(head);
  if (found !== null) return found;
  const all = decodeLoose(data);
  return all === null ? null : imageSize(all);
}

const note = (text: string | undefined): string => (text ? ` (${text})` : "");

/** What in `parts` breaks `limits`: one sentence each, then the fix. `[]` when it fits. */
export function requestProblems(parts: readonly Part[], limits: Limits): string[] {
  const images = parts.filter((p): p is Extract<Part, { type: "image" }> => p.type === "image");
  const texts = parts.filter((p): p is Extract<Part, { type: "text" }> => p.type === "text");
  const pictureBytes = images.reduce((sum, p) => sum + (p.data || "").length, 0);
  const total = pictureBytes + texts.reduce((sum, p) => sum + jsonSize(p.text || ""), 0) + 100 * parts.length + 200;

  const problems: string[] = [];
  let sizeProblem = false;
  if (total > limits.requestBytes) {
    sizeProblem = true;
    problems.push(`the request is ${mb(total)}; ${limits.provider} accepts ${mb(limits.requestBytes)}${note(limits.requestNote)}`);
  }
  const countProblem = images.length > limits.images;
  if (countProblem) {
    problems.push(`it has ${images.length} pictures; ${limits.provider} accepts ${limits.images}${note(limits.imagesNote)}`);
  }
  if (limits.imageB64Bytes !== undefined) {
    const tooBig = images.filter((p) => (p.data || "").length > limits.imageB64Bytes!);
    if (tooBig.length > 0) {
      sizeProblem = true;
      const largest = Math.max(...tooBig.map((p) => p.data.length));
      const what = tooBig.length === 1 ? "a picture is" : `${tooBig.length} pictures are up to`;
      problems.push(`${what} ${mb(largest)} (base64); ${limits.provider} accepts ${mb(limits.imageB64Bytes)}${note(limits.imageNote)}`);
    }
  }
  const odd = [...new Set(images.map((p) => p.media_type).filter((t) => t != null && !limits.mediaTypes.includes(t)))].sort();
  if (odd.length > 0) {
    const accepted = limits.mediaTypes.map((t) => t.split("/").at(-1)!).sort();
    problems.push(`a picture is ${odd.join(", ")}; ${limits.provider} accepts ${accepted.join(", ")}`);
  }
  if (limits.maxSide !== undefined) {
    const many = limits.manyImages !== undefined && images.length > limits.manyImages;
    const side = many && limits.manySide ? limits.manySide : limits.maxSide;
    const sizes = images.map((p) => size(p.data || "")).filter((s): s is [number, number] => s !== null);
    const over = sizes.filter((s) => Math.max(...s) > side);
    if (over.length > 0) {
      sizeProblem = true;
      // Python's max(key=max): the first of the largest.
      let biggest = over[0]!;
      for (const s of over) if (Math.max(...s) > Math.max(...biggest)) biggest = s;
      const why = many && side === limits.manySide ? ` when a request has more than ${limits.manyImages} pictures` : "";
      problems.push(`${over.length} picture(s) up to ${biggest[0]}x${biggest[1]} px; ${limits.provider} accepts ${side} px a side${why}`);
    }
  }
  if (problems.length === 0) return [];

  const fixes: string[] = [];
  if (sizeProblem && images.length > 0) {
    const png = images.filter((p) => p.media_type === "image/png").reduce((sum, p) => sum + p.data.length, 0);
    if (png > pictureBytes / 2) fixes.push("image_format: jpeg (scans and photos several times smaller)");
    fixes.push("max_dim: 1568 (Claude's standard models see no more)");
  }
  if (countProblem || (sizeProblem && images.length > 1)) {
    const half = Math.max(1, Math.floor(Math.min(images.length, limits.images) / 2));
    fixes.push(`fewer pages per request, e.g. pages: ${half === 1 ? "1" : `1-${half}`}`);
  } else if (sizeProblem && images.length === 0) {
    fixes.push("fewer files or pages per request");
  }
  if (odd.length > 0) fixes.push("image_format: png (converts the picture)");
  if (fixes.length > 0) problems.push(`Fix: ${fixes.join("; ")}`);
  return problems;
}

/** Warn (`RequestLimitWarning`) when `parts` break `limits`. */
export function checkRequest(parts: readonly Part[], limits: Limits): void {
  const problems = requestProblems(parts, limits);
  if (problems.length === 0) return;
  const body = problems.map((p) => (p.startsWith("Fix:") ? `  ${p}` : `  - ${p}`)).join("\n");
  warn(`This ${limits.provider} request would be rejected:\n${body}`, "RequestLimitWarning");
}
