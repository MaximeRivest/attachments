/**
 * `Artifacts`: what `att()` gives. An `Array` of plain artifact objects
 * with the methods that turn them into what a model reads.
 */

import {
  chunk,
  type ChunkOptions,
  estimateTokens,
  type PresentOptions,
  renderText,
  toClaudeMessages,
  toLm15Message,
  toOpenAIMessages,
  toParts,
} from "./present.ts";
import { errorSummary, errorsOf, summary } from "./summary.ts";
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
import { artifactFromWire, artifactToWire } from "./wire.ts";

const INSPECT = Symbol.for("nodejs.util.inspect.custom");

/**
 * Thrown by {@link Artifacts.throwIfErrors} when inputs failed. `att()`
 * itself never throws for a bad file; this is the opt-in stop.
 */
export class AttachmentsError extends Error {
  override name = "AttachmentsError";
  /** Every failure: the same objects as `Artifacts.errors`. */
  readonly errors: ErrorInfo[];
  /** The whole result, the files that worked included. */
  readonly artifacts: Artifacts;

  constructor(errors: readonly ErrorInfo[], artifacts: Artifacts = new Artifacts()) {
    super(errorSummary(errors));
    this.errors = [...errors];
    this.artifacts = artifacts;
  }
}

/**
 * The artifacts of one `att()` call, in input order. A real array: index
 * it, loop over it, spread it. `filter`, `slice` and `concat` keep the
 * methods; `map` gives a plain array.
 *
 * @example
 * const a = await att("report.pdf");
 * a.text;                 // the prompt text, file names included
 * a.claude("Summarize."); // Anthropic messages
 * a[0].meta.source;       // "report.pdf"
 */
export class Artifacts extends Array<Artifact> {
  /** `map`, `flatMap` and the like make plain arrays: their elements need not be artifacts. */
  static override get [Symbol.species](): ArrayConstructor {
    return Array;
  }

  /** Artifacts from any list of artifacts. */
  static override from(items: Iterable<Artifact> | ArrayLike<Artifact>): Artifacts;
  static override from<T, U>(items: Iterable<T> | ArrayLike<T>, map: (v: T, k: number) => U, thisArg?: unknown): U[];
  static override from(items: Iterable<unknown> | ArrayLike<unknown>, map?: (v: unknown, k: number) => unknown, thisArg?: unknown): unknown {
    const list = map ? Array.from(items, map, thisArg) : Array.from(items);
    const out = new Artifacts();
    out.push(...(list as Artifact[]));
    return out;
  }

  /** Artifacts from their JSON wire form ({@link toWire}); throws on bad data. */
  static fromWire(data: unknown): Artifacts {
    if (!Array.isArray(data)) {
      throw new TypeError(`fromWire expects an array of artifacts, got ${data === null ? "null" : typeof data}`);
    }
    return Artifacts.from(data.map(artifactFromWire));
  }

  override filter<S extends Artifact>(predicate: (value: Artifact, index: number, array: Artifact[]) => value is S, thisArg?: unknown): Artifacts;
  override filter(predicate: (value: Artifact, index: number, array: Artifact[]) => unknown, thisArg?: unknown): Artifacts;
  override filter(predicate: (value: Artifact, index: number, array: Artifact[]) => unknown, thisArg?: unknown): Artifacts {
    return Artifacts.from(Array.prototype.filter.call(this, predicate, thisArg) as Artifact[]);
  }

  override slice(start?: number, end?: number): Artifacts {
    return Artifacts.from(Array.prototype.slice.call(this, start, end) as Artifact[]);
  }

  override concat(...items: (Artifact | ConcatArray<Artifact>)[]): Artifacts {
    return Artifacts.from(Array.prototype.concat.apply(Array.from(this), items) as Artifact[]);
  }

  /** The prompt text, file names included (`toText({ sources: false })` hides them). */
  get text(): string {
    return renderText(this);
  }

  /** Every picture of every artifact. */
  get images(): ImageItem[] {
    return this.flatMap((a) => a.images ?? []);
  }

  /** `{ source, code, message }` for each artifact that failed. */
  get errors(): ErrorInfo[] {
    return errorsOf(this);
  }

  /** Estimated tokens, text and pictures: a budget figure (`estimateTokens().total`). */
  get tokens(): number {
    return estimateTokens(this).total;
  }

  /** The prompt text; `sources: false` keeps file names out. */
  toText({ sources = true }: { sources?: boolean | undefined } = {}): string {
    return renderText(this, { sources });
  }

  /** Provider-neutral parts, each page's pictures right after its text. */
  parts(options: PresentOptions & { prompt?: string | undefined } = {}): Part[] {
    return toParts(this, options);
  }

  /** Claude Messages API `messages`; warns when a published limit is broken. */
  claude(prompt?: string, options: PresentOptions = {}): ClaudeMessage[] {
    return toClaudeMessages(this, prompt, options);
  }

  /** OpenAI Chat Completions `messages`; warns when a published limit is broken. */
  openai(prompt?: string, options: PresentOptions = {}): OpenAIMessage[] {
    return toOpenAIMessages(this, prompt, options);
  }

  /**
   * One lm15 `Message` from the user, for `@lm15/lm15`. Without a prompt
   * the document is a message of its own, a prefix providers can cache.
   */
  lm15(prompt?: string, options: PresentOptions = {}): Lm15Message {
    return toLm15Message(this, prompt, options);
  }

  /** Chunks for retrieval, page by page. */
  chunk(options: ChunkOptions = {}): string[] {
    return chunk(this, options);
  }

  /** `{ text, images, total }` tokens, pictures as Claude counts them for `tier`. */
  estimateTokens({ tier = "high" }: { tier?: Tier | undefined } = {}): TokenEstimate {
    return estimateTokens(this, { tier });
  }

  /**
   * Throw an {@link AttachmentsError} listing every failure, if any;
   * otherwise return the artifacts. Every input was read first, so the
   * error carries the files that worked too.
   */
  throwIfErrors(): this {
    const errors = this.errors;
    if (errors.length > 0) throw new AttachmentsError(errors, this);
    return this;
  }

  /** The JSON wire form: pictures as base64 `bytes_b64`. New objects; `this` is untouched. */
  toWire(): WireArtifact[] {
    return Array.from(this, artifactToWire);
  }

  /** `JSON.stringify(a)` writes the wire form. */
  toJSON(): WireArtifact[] {
    return this.toWire();
  }

  /** The prompt text: `${a}` and `String(a)`. */
  override toString(): string {
    return this.text;
  }

  /** What `console.log(a)` shows in Node: the summary, never text or bytes. */
  [INSPECT](): string {
    return summary(this);
  }
}
