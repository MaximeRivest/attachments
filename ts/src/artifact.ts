/**
 * Building artifacts (contract/IR-CONTRACT.md, "Helper API"), for
 * processors of your own and for this package.
 */

import type { Artifact, ErrorCode, ImageItem, Meta } from "./types.ts";

/** An artifact with safe defaults. */
export function makeArtifact({
  text = "",
  images = [],
  audio = [],
  video = [],
  meta = {},
}: { text?: string; images?: ImageItem[]; audio?: unknown[]; video?: unknown[]; meta?: Partial<Meta> } = {}): Artifact {
  return { text, images, audio, video, meta: meta as Meta };
}

/** A failed artifact: `meta.error` with a code and a message for people. */
export function errorArtifact(source: string, code: ErrorCode, message: string): Artifact {
  return makeArtifact({ meta: { source, error: { code, message } } });
}

/** What reads a format in TypeScript is missing: the service may read it instead. */
export function missingDepArtifact(source: string, feature: string, remedy?: string): Artifact {
  const how =
    remedy ??
    `no TypeScript reader yet; the Attachments service reads it: configure({ serviceUrl: "https://api.attachments.dev/v1" }) or set an API key`;
  return errorArtifact(source, "missing-dependency", `Processing '${source}' requires optional dependencies for '${feature}': ${how}`);
}

export function isMissingDependency(artifact: Artifact): boolean {
  return artifact.meta?.error?.code === "missing-dependency";
}

/** `meta.extra` key naming the feature a result lacked for one of its parts. */
export const MISSING_PART = "missing_dependency";

/** A part asked for (pictures) was not made: the text stays, a warning says why. Changes `artifact`. */
export function missingPart(artifact: Artifact, feature: string, part: string, remedy: string): Artifact {
  artifact.meta.extra = { ...(artifact.meta.extra ?? {}), [MISSING_PART]: feature };
  (artifact.meta.warnings ??= []).push(`${part} not made: it needs ${feature} — ${remedy}`);
  return artifact;
}

/** Missing a dependency (nothing read) or a part: the service may be asked. */
export function lacksDependency(artifact: Artifact): boolean {
  return isMissingDependency(artifact) || typeof artifact.meta?.extra?.[MISSING_PART] === "string";
}

/** Every required key filled; `meta.source` set when absent. Changes and returns `artifact`. */
export function normalizeArtifact(artifact: Partial<Artifact>, source: string): Artifact {
  artifact.text ??= "";
  artifact.images ??= [];
  artifact.audio ??= [];
  artifact.video ??= [];
  artifact.meta ??= {} as Meta;
  artifact.meta.source ??= source;
  return artifact as Artifact;
}

export function attachWarnings(artifact: Artifact, warnings: readonly string[]): Artifact {
  if (warnings.length > 0) (artifact.meta.warnings ??= []).push(...warnings);
  return artifact;
}
