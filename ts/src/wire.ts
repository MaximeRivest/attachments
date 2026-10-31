/**
 * The JSON wire form (contract/IR-CONTRACT.md, "Wire format"): images
 * carry `bytes_b64` instead of `bytes`. What the server sends, what
 * `JSON.stringify` writes, what `contract/artifact.schema.json` checks.
 */

import { decodeStrict, encode } from "./base64.ts";
import type { Artifact, WireArtifact } from "./types.ts";

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value) && !(value instanceof Uint8Array);
}

/** The wire form of one artifact: a new object, the input untouched. */
export function artifactToWire(artifact: Artifact): WireArtifact {
  const out: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(artifact)) {
    if (key !== "images") {
      out[key] = structuredClone(value);
      continue;
    }
    out[key] = ((value as unknown[] | undefined) ?? []).map((image) => {
      const item: Record<string, unknown> = {};
      const raw = (image as Record<string, unknown>)["bytes"];
      for (const [k, v] of Object.entries(image as Record<string, unknown>)) {
        if (k === "bytes_b64" && raw !== undefined) continue;
        if (k === "bytes") {
          if (!(v instanceof Uint8Array)) {
            throw new TypeError(`image ${JSON.stringify((image as { name?: unknown }).name)}: 'bytes' must be a Uint8Array`);
          }
          item["bytes_b64"] = encode(v);
        } else {
          item[k] = structuredClone(v);
        }
      }
      return item;
    });
  }
  return out as unknown as WireArtifact;
}

/**
 * Rebuild an artifact from its wire form: images get their `bytes` back.
 * Bad data throws instead of losing a picture quietly: `TypeError` for a
 * value of the wrong kind, `SyntaxError` for invalid base64. Missing keys
 * are filled with empty values; `meta.source` is never invented.
 */
export function artifactFromWire(data: unknown): Artifact {
  if (!isObject(data)) {
    throw new TypeError(`an artifact must be an object, got ${describe(data)}`);
  }
  const out = structuredClone(data) as Record<string, unknown>;
  const meta = out["meta"] ?? {};
  if (!isObject(meta)) throw new TypeError(`'meta' must be an object, got ${describe(meta)}`);
  const where = typeof meta["source"] === "string" && meta["source"] ? meta["source"] : "(unknown)";
  if (typeof (out["text"] ?? "") !== "string") throw new TypeError(`${where}: 'text' must be a string`);
  const images = out["images"] ?? [];
  if (!Array.isArray(images)) throw new TypeError(`${where}: 'images' must be a list`);
  out["images"] = images.map((image: unknown) => {
    if (!isObject(image)) throw new TypeError(`${where}: each image must be an object`);
    const name = typeof image["name"] === "string" && image["name"] ? image["name"] : "image";
    const item: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(image)) {
      if (key !== "bytes_b64") {
        item[key] = value;
        continue;
      }
      if ("bytes" in image) continue;
      if (typeof value !== "string") throw new TypeError(`${where}: image '${name}' has a non-string 'bytes_b64'`);
      const bytes = decodeStrict(value);
      if (bytes === null) throw new SyntaxError(`${where}: image '${name}' has invalid base64 in 'bytes_b64'`);
      item["bytes"] = bytes;
    }
    return item;
  });
  out["text"] ??= "";
  out["audio"] ??= [];
  out["video"] ??= [];
  out["meta"] = meta;
  return out as unknown as Artifact;
}

function describe(value: unknown): string {
  if (value === null) return "null";
  if (Array.isArray(value)) return "an array";
  return typeof value;
}
