/**
 * Attachments: turn any file, folder or web page into text and pictures a
 * language model can read.
 *
 * @example
 * import { att } from "attachments-dev";
 * const messages = await att("report.pdf[pages: 1-4]").claude("Summarize.");
 *
 * @packageDocumentation
 */

export { att, type Att, type AttOptions, type FromPromptOptions, type Input, type OptionCatalog, type PendingArtifacts } from "./att.ts";
export { AttachmentsError, Artifacts } from "./artifacts.ts";
export { configure, type Prefer, type Settings } from "./config.ts";
export { checkDeps } from "./deps.ts";
export type { ChunkOptions, PresentOptions } from "./present.ts";
export type { Options } from "./generated/options.ts";
export type {
  Artifact,
  ArtifactError,
  ClaudeBlock,
  ClaudeImageType,
  ClaudeMessage,
  ErrorCode,
  ErrorInfo,
  ImageItem,
  Lm15Message,
  Lm15Part,
  Meta,
  OpenAIMessage,
  OpenAIPart,
  Part,
  Segment,
  Tier,
  TokenEstimate,
  WireArtifact,
  WireImage,
} from "./types.ts";
