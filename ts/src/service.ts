/**
 * The service client (contract/server.md): `POST /process` with the file
 * and its options, `POST /unpack` with an address.
 *
 * @internal
 */

import { decodeStrict } from "./base64.ts";
import type { Effective } from "./config.ts";
import type { Artifact } from "./types.ts";
import { artifactFromWire } from "./wire.ts";

/** The service did not give an artifact. */
export class ServiceError extends Error {
  override name = "ServiceError";
  readonly status: number | null;

  constructor(message: string, status: number | null = null) {
    super(message);
    this.status = status;
  }
}

/** A form field name or file name, escaped as httpx (and the HTML5 form encoding) escape them. */
const escapeName = (s: string): string =>
  s.replace(/["\\\u0000-\u001a\u001c-\u001f]/gu, (c) =>
    c === '"' ? "%22" : c === "\\" ? "\\\\" : `%${c.charCodeAt(0).toString(16).toUpperCase().padStart(2, "0")}`,
  );

const encoder = new TextEncoder();

function multipart(fields: [string, string][], filename: string, data: Uint8Array): { body: Uint8Array; type: string } {
  const boundary = `attachments-${crypto.randomUUID().replaceAll("-", "")}`;
  const chunks: Uint8Array[] = [];
  for (const [name, value] of fields) {
    chunks.push(encoder.encode(`--${boundary}\r\nContent-Disposition: form-data; name="${escapeName(name)}"\r\n\r\n${value}\r\n`));
  }
  chunks.push(
    encoder.encode(
      `--${boundary}\r\nContent-Disposition: form-data; name="file"; filename="${escapeName(filename)}"\r\n` +
        "Content-Type: application/octet-stream\r\n\r\n",
    ),
    data,
    encoder.encode(`\r\n--${boundary}--\r\n`),
  );
  const body = new Uint8Array(chunks.reduce((n, c) => n + c.length, 0));
  let at = 0;
  for (const c of chunks) {
    body.set(c, at);
    at += c.length;
  }
  return { body, type: `multipart/form-data; boundary=${boundary}` };
}

async function post(settings: Effective, route: string, init: { body: Uint8Array | string; type: string }, signal?: AbortSignal): Promise<unknown> {
  if (!settings.serviceConfigured) {
    throw new ServiceError(
      "Service not configured. Set configure({ apiKey }) for the hosted service, or configure({ serviceUrl }) for a keyless or self-hosted server.",
    );
  }
  const timeout = AbortSignal.timeout(settings.timeout * 1000);
  let response: Response;
  try {
    response = await fetch(`${settings.serviceUrl}${route}`, {
      method: "POST",
      headers: { "Content-Type": init.type, ...(settings.apiKey ? { Authorization: `Bearer ${settings.apiKey}` } : {}) },
      body: init.body as BodyInit,
      signal: signal ? AbortSignal.any([signal, timeout]) : timeout,
    });
  } catch (err) {
    if (signal?.aborted) throw signal.reason;
    if ((err as Error).name === "TimeoutError") throw new ServiceError(`Service request timed out after ${settings.timeout}s`);
    throw new ServiceError(`Service request failed: ${(err as Error).message}${(err as { cause?: Error }).cause ? ` (${(err as { cause: Error }).cause.message})` : ""}`);
  }
  const text = await response.text();
  if (response.status === 401) throw new ServiceError("Invalid API key", 401);
  if (response.status === 402) throw new ServiceError("API quota exceeded", 402);
  if (response.status === 413) throw new ServiceError("File too large for service", 413);
  if (response.status >= 400) {
    let detail = text;
    try {
      const parsed = JSON.parse(text) as { error?: unknown };
      if (typeof parsed?.error === "string") detail = parsed.error;
    } catch {
      /* the body as it came */
    }
    throw new ServiceError(`Service error: ${detail}`, response.status);
  }
  try {
    return JSON.parse(text);
  } catch {
    throw new ServiceError("Service returned an invalid artifact: not JSON");
  }
}

/** Read one file with the service: the artifact it answers. Throws {@link ServiceError}. */
export async function processViaService(
  settings: Effective,
  filename: string,
  data: Uint8Array,
  options: Record<string, unknown>,
  signal?: AbortSignal,
): Promise<Artifact> {
  const fields: [string, string][] = Object.entries(options)
    .filter(([, v]) => v !== undefined && v !== null)
    .map(([k, v]) => [k, JSON.stringify(v)]);
  const result = await post(settings, "/process", multipart(fields, filename, data), signal);
  try {
    return artifactFromWire(result);
  } catch (err) {
    throw new ServiceError(`Service returned an invalid artifact: ${(err as Error).message}`);
  }
}

/** The files at an address, unpacked by the service. Throws {@link ServiceError}. */
export async function unpackViaService(settings: Effective, url: string, signal?: AbortSignal): Promise<{ name: string; data: Uint8Array }[]> {
  const result = (await post(settings, "/unpack", { body: JSON.stringify({ url }), type: "application/json" }, signal)) as {
    files?: { filename?: unknown; data_b64?: unknown }[];
  };
  return (result.files ?? []).map((f) => {
    const data = typeof f.data_b64 === "string" ? decodeStrict(f.data_b64) : null;
    if (typeof f.filename !== "string" || data === null) throw new ServiceError("Service returned an invalid file list");
    return { name: f.filename, data };
  });
}
