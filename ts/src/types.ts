/**
 * The Artifact (contract/IR-CONTRACT.md): what every processor makes and
 * every consumer reads. Plain objects; optional keys are absent, never
 * `null` or `undefined`.
 */

/** The error codes of the contract. */
export type ErrorCode =
  | "missing-dependency"
  | "password-required"
  | "parse-error"
  | "unpack-error"
  | "service-error"
  | "invalid-option"
  | "processing-error";

/** A failure, on `meta.error`. */
export interface ArtifactError {
  code: ErrorCode;
  /** For people; includes the remedy when one is known. Not pinned by the contract. */
  message: string;
}

/** A failure as `Artifacts.errors` lists it. */
export interface ErrorInfo {
  source: string;
  code: ErrorCode | "";
  message: string;
}

/** A part of an artifact's text: a page, sheet, slide or section. Offsets count code points. */
export interface Segment {
  kind: "page" | "sheet" | "slide" | "section" | (string & {});
  /** For people (a slide's label is its title); never parse it. */
  label: string;
  /** Offset into `text`, inclusive, in code points. */
  start: number;
  /** Offset into `text`, exclusive, in code points. */
  end: number;
  /** 1-based page, slide or sheet number; the same number its images carry. */
  page?: number;
}

/** A picture: a page drawn, an embedded image, a photo. */
export interface ImageItem {
  name: string;
  mimetype: string;
  bytes: Uint8Array;
  /** 1-based page or slide it shows or comes from. */
  page?: number;
}

export interface Meta {
  /** Where it came from: a path, an address, a file name. */
  source: string;
  kind?: "text" | "pdf" | "table" | "document" | "html" | "slides" | "image" | "directory" | (string & {});
  /** `"service"` when a server made it. */
  via?: "service";
  error?: ArtifactError;
  /** Information, not a failure (e.g. "no processor available"). */
  note?: string;
  /** Something asked for did not happen (an unknown option, OCR stopped early). */
  warnings?: string[];
  segments?: Segment[];
  /** Processor-specific details. */
  extra?: Record<string, unknown>;
}

/** What a processor makes of one file. */
export interface Artifact {
  text: string;
  images: ImageItem[];
  /** Reserved. */
  audio: unknown[];
  /** Reserved. */
  video: unknown[];
  meta: Meta;
}

/** An image in the JSON wire form: `bytes_b64` instead of `bytes`. */
export interface WireImage {
  name: string;
  mimetype: string;
  bytes_b64: string;
  page?: number;
}

/** An artifact in the JSON wire form (contract/artifact.schema.json). */
export interface WireArtifact {
  text: string;
  images: WireImage[];
  audio: unknown[];
  video: unknown[];
  meta: Meta;
}

/** A provider-neutral content part (`Artifacts.parts()`). */
export type Part =
  | { type: "text"; text: string }
  | { type: "image"; media_type: string; data: string };

/** The picture types Claude accepts. */
export type ClaudeImageType = "image/jpeg" | "image/png" | "image/gif" | "image/webp";

/**
 * Claude Messages API content block, as `@anthropic-ai/sdk`'s `MessageParam`
 * takes it. A picture of another type keeps its real type at run time
 * (Claude refuses it, and building the messages warns: `RequestLimitWarning`).
 */
export type ClaudeBlock =
  | { type: "text"; text: string }
  | { type: "image"; source: { type: "base64"; media_type: ClaudeImageType; data: string } };

/** One Claude Messages API message. */
export interface ClaudeMessage {
  role: "user";
  content: ClaudeBlock[];
}

/** OpenAI Chat Completions content part. */
export type OpenAIPart =
  | { type: "text"; text: string }
  | { type: "image_url"; image_url: { url: string } };

/** One OpenAI Chat Completions message. */
export interface OpenAIMessage {
  role: "user";
  content: OpenAIPart[];
}

/** An lm15 text or image part, as `@lm15/lm15` types them. */
export type Lm15Part =
  | { readonly type: "text"; readonly text: string }
  | { readonly type: "image"; readonly mediaType: string; readonly data: string };

/** One lm15 `Message` from the user: plain data, accepted by `@lm15/lm15` as is. */
export interface Lm15Message {
  readonly role: "user";
  readonly parts: readonly Lm15Part[];
}

/** `Artifacts.estimateTokens()`: a budget figure, not a bill. */
export interface TokenEstimate {
  text: number;
  images: number;
  total: number;
}

/** Claude's picture resolution tiers: `high` (Claude 4.7 and later), `standard` (others). */
export type Tier = "high" | "standard";
