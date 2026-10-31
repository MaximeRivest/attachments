/**
 * One file through its processor, locally or with the service, by
 * `prefer` (contract/reading.md, "Routing a file").
 *
 * @internal
 */

import { attachWarnings, errorArtifact, isMissingDependency, lacksDependency, makeArtifact } from "./artifact.ts";
import type { Effective } from "./config.ts";
import { closeMatch } from "./difflib.ts";
import { Written } from "./dsl.ts";
import { declaredOptions, type OptionDecl, plainOptions, resolveOptions } from "./options.ts";
import {
  extension,
  type NamedProcessor,
  namedProcessors,
  type ProcessorContext,
  type ProcessorFn,
  routeProcessor,
  STANDARD,
} from "./processors.ts";
import { processViaService, ServiceError } from "./service.ts";
import type { Artifact } from "./types.ts";
import { warn } from "./warn.ts";

export interface FileJob {
  filename: string;
  data: Uint8Array;
  /** Raw options: the string's (as {@link Written}) and the call's. */
  options: Record<string, unknown>;
  settings: Effective;
  /** The address it was downloaded from. */
  url?: string | undefined;
  signal?: AbortSignal | undefined;
}

function optionContext(filename: string, key: string): string {
  const ext = extension(filename);
  return ext || (key === "__text__" ? "text" : key);
}

function fromError(source: string, err: unknown, context: string): Artifact {
  const e = err as { code?: string; message?: string };
  if (e?.code === "ERR_MODULE_NOT_FOUND" || e?.code === "MODULE_NOT_FOUND") {
    return errorArtifact(source, "missing-dependency", `${context} processing failed: ${e.message}. Missing optional dependency — install it.`);
  }
  return errorArtifact(source, "processing-error", `${context} processing failed: ${e?.message ?? String(err)}`);
}

async function chooseNamed(
  table: Map<string, NamedProcessor>,
  data: Uint8Array,
  filename: string,
  requested: unknown,
  context: string,
  warnings: string[],
): Promise<NamedProcessor | null> {
  if (requested !== undefined && requested !== null) {
    const wanted = String(requested).trim().toLowerCase();
    if (wanted === STANDARD) return null;
    const found = table.get(wanted);
    if (found) return found;
    const names = [STANDARD, ...table.keys()];
    let message = `Unknown processor '${String(requested)}' for ${context}`;
    const close = closeMatch(wanted, names);
    if (close) message += ` — did you mean '${close}'?`;
    message += ` (available: ${names.join(", ")})`;
    warnings.push(message);
    warn(message, "OptionWarning");
  }
  for (const entry of [...table.values()].reverse()) {
    if (!entry.detect) continue;
    try {
      if (await entry.detect(data, filename)) return entry;
    } catch {
      /* a detect that throws says no */
    }
  }
  return null;
}

/** One file to one artifact (not yet normalized). */
export async function processFile(job: FileJob): Promise<Artifact> {
  const { filename, data, settings } = job;
  let options: Record<string, unknown> = { ...job.options };
  const [proc, key] = routeProcessor(filename, data);
  const context = optionContext(filename, key);
  const ext = extension(filename);
  const table = (ext ? namedProcessors.get(ext) : undefined) ?? namedProcessors.get(key);
  let requested = options["processor"];
  delete options["processor"];
  if (requested instanceof Written) requested = requested.text;
  const choiceWarnings: string[] = [];
  let named: NamedProcessor | null = null;
  if (table && table.size > 0) named = await chooseNamed(table, data, filename, requested, context, choiceWarnings);
  else if (requested !== undefined && String(requested).trim().toLowerCase() !== STANDARD && proc !== null) {
    const message = `Unknown processor '${String(requested)}' for ${context} — only the standard one (${STANDARD}) reads it`;
    choiceWarnings.push(message);
    warn(message, "OptionWarning");
  }

  let standardSchema: readonly OptionDecl[] = proc !== null ? declaredOptions(key) : [];
  let schema = standardSchema;
  if (named !== null) {
    const own = named.options;
    const ownNames = new Set(own.map((o) => o.name));
    standardSchema = standardSchema.filter((o) => !ownNames.has(o.name));
    schema = [...standardSchema, ...own];
  }
  let resolved: Record<string, unknown> = {};
  let warnings: string[] = [];
  if (proc !== null || named !== null) {
    const r = resolveOptions(schema, options, context);
    resolved = r.options;
    warnings = r.warnings;
    for (const w of warnings) warn(w, "OptionWarning");
    if (job.url && !("url" in resolved) && schema.some((o) => o.name === "url")) {
      resolved["url"] = job.url;
      options = { ...options, url: job.url };
    }
  }
  // Labels on pictures are drawn by the service: TypeScript does not draw.
  let watermark: unknown;
  if (schema.some((o) => o.name === "watermark")) {
    watermark = resolved["watermark"];
    delete resolved["watermark"];
  }
  options = plainOptions(schema, options);

  const standard = (d: Uint8Array, kwargs: Record<string, unknown>, warns: string[], raw: Record<string, unknown>): Promise<Artifact> =>
    runStandard(filename, d, proc, kwargs, warns, raw, settings, job.signal);

  let result: Artifact;
  if (named !== null) {
    const standardNames = new Set(standardSchema.flatMap((o) => [o.name, ...o.aliases, ...(o.param ? [o.param] : [])]));
    const standardRaw = Object.fromEntries(Object.entries(options).filter(([k]) => standardNames.has(k)));
    const standardKwargs = Object.fromEntries(Object.entries(resolved).filter(([k]) => standardSchema.some((o) => o.name === k)));
    const ctx: ProcessorContext = {
      filename,
      signal: job.signal,
      async base(other, more = {}) {
        const kwargs = { ...standardKwargs };
        let moreWarnings: string[] = [];
        if (Object.keys(more).length > 0) {
          const r = resolveOptions(standardSchema, more, `base of processor '${named!.name}'`);
          moreWarnings = r.warnings;
          Object.assign(kwargs, r.options);
        }
        return standard(other ?? data, kwargs, moreWarnings, { ...standardRaw, ...more });
      },
    };
    try {
      result = await named.fn(data, resolved as never, ctx);
    } catch (err) {
      result = fromError(filename, err, `processor '${named.name}'`);
    }
    if (typeof result !== "object" || result === null) {
      result = errorArtifact(filename, "processing-error", `processor '${named.name}' returned ${typeof result}, not an artifact (use makeArtifact)`);
    }
    attachWarnings(result, warnings);
    result.meta ??= {} as Artifact["meta"];
    result.meta.extra = { ...(result.meta.extra ?? {}), processor: named.name };
  } else {
    // `options` keeps `watermark`: the service draws the labels.
    result = await standard(data, resolved, warnings, options);
    if (watermark !== undefined && result.meta?.via !== "service" && (result.images?.length ?? 0) > 0) {
      attachWarnings(result, ["watermark: labels are drawn by the service; this file was read here, so its pictures have none"]);
    }
  }
  if (choiceWarnings.length > 0) {
    result.meta ??= {} as Artifact["meta"];
    result.meta.warnings = [...choiceWarnings, ...(result.meta.warnings ?? [])];
  }
  return result;
}

async function viaService(settings: Effective, filename: string, data: Uint8Array, options: Record<string, unknown>, signal?: AbortSignal): Promise<Artifact> {
  try {
    const result = await processViaService(settings, filename, data, options, signal);
    result.meta.via = "service";
    return result;
  } catch (err) {
    if (err instanceof ServiceError) return errorArtifact(filename, "service-error", `service error: ${err.message}`);
    throw err;
  }
}

async function runStandard(
  filename: string,
  data: Uint8Array,
  proc: ProcessorFn | null,
  resolved: Record<string, unknown>,
  warnings: string[],
  raw: Record<string, unknown>,
  settings: Effective,
  signal?: AbortSignal,
): Promise<Artifact> {
  const runLocal = async (): Promise<Artifact> => {
    const ctx: ProcessorContext = {
      filename,
      signal,
      base: () => Promise.reject(new Error("base() is for named processors")),
    };
    try {
      return attachWarnings(await proc!(data, resolved as never, ctx), warnings);
    } catch (err) {
      return fromError(filename, err, "local");
    }
  };
  const empty = (note: string): Artifact => makeArtifact({ meta: { source: filename, note } });
  const svc = settings.serviceConfigured;
  switch (settings.prefer) {
    case "service-only":
      if (!svc) {
        return errorArtifact(
          filename,
          "service-error",
          "service-only mode but no service configured (configure({ apiKey }) or configure({ serviceUrl }))",
        );
      }
      return viaService(settings, filename, data, raw, signal);
    case "local-only":
      return proc === null ? empty("no local processor available") : runLocal();
    case "service": {
      if (svc) {
        const served = await viaService(settings, filename, data, raw, signal);
        if (!served.meta?.error) return served;
      }
      return proc === null ? empty("no processor available") : runLocal();
    }
    default: {
      let partial: Artifact | null = null;
      if (proc !== null) {
        const result = await runLocal();
        if (!svc || !lacksDependency(result)) return result;
        if (!isMissingDependency(result)) partial = result;
      }
      if (svc) {
        const served = await viaService(settings, filename, data, raw, signal);
        if (partial !== null && served.meta?.error) {
          (partial.meta.warnings ??= []).push(`The service could not make the missing part either: ${served.meta.error.message ?? ""}`);
          return partial;
        }
        return served;
      }
      return empty("no processor available");
    }
  }
}
