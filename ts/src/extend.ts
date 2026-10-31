/**
 * For people who write their own processors and sources, and for tools
 * that read the option syntax. `import { … } from "attachments-dev/extend"`.
 *
 * @packageDocumentation
 */

import { type OptionDecl, type OptionType, registerOptions } from "./options.ts";
import type { PageSelection } from "./pages.ts";
import { namedProcessors, normalizeKey, type ProcessorContext, type ProcessorFn, processors, STANDARD } from "./processors.ts";
import { sources, type SourceSpec } from "./sources/index.ts";
import type { Artifact } from "./types.ts";

export {
  attachWarnings,
  errorArtifact,
  isMissingDependency,
  lacksDependency,
  makeArtifact,
  missingDepArtifact,
  missingPart,
  normalizeArtifact,
} from "./artifact.ts";
export { type DslValue, formatDsl, parseDsl } from "./dsl.ts";
export { declaredOptions, type OptionDecl, type OptionType, type OptionValue, resolveOptions } from "./options.ts";
export { PageSelection, PageSelectionError, parsePages } from "./pages.ts";
export { imageTokens } from "./present.ts";
export type { ProcessorContext } from "./processors.ts";
export type { SourceSpec } from "./sources/index.ts";
export { artifactFromWire, artifactToWire } from "./wire.ts";

/** One option a processor declares. */
export interface OptionSpec<T extends OptionType = OptionType> {
  type: T;
  default?: unknown;
  /** One line for people: shown by `att.options()` and editors. */
  help?: string;
  /** Other spellings accepted in the string (`pw` for `password`). */
  aliases?: readonly string[];
  /** A usage example, `"currency: EUR"`. */
  example?: string;
}

interface TypeOf {
  str: string;
  int: number;
  float: number;
  bool: boolean;
  pages: PageSelection;
  bool_or_auto: boolean | "auto" | "always";
  str_or_int: string | number;
}

/** The resolved options a processor receives, typed from its declarations. */
export type ResolvedOptions<O extends Record<string, OptionSpec>> = { [K in keyof O]?: TypeOf[O[K]["type"]] } & Record<string, unknown>;

export interface ProcessorSpec<O extends Record<string, OptionSpec>> {
  /** The extensions it reads (`".pdf"`, `"pdf"`). */
  extensions: readonly string[];
  /**
   * Without a name, it becomes the processor of these extensions. With a
   * name it lives next to the standard one: chosen by `[processor: NAME]`,
   * or by `detect`; its result's `meta.extra.processor` names it.
   */
  name?: string;
  /** For a named processor: choose it for the files where this says yes (keep it cheap). */
  detect?: (data: Uint8Array, filename: string) => boolean | Promise<boolean>;
  /** Its options, by name (for a named processor, on top of the standard ones). */
  options?: O;
  /** Read one file. Never throw for a bad file: return `errorArtifact(...)`. */
  process(data: Uint8Array, options: ResolvedOptions<O>, context: ProcessorContext): Artifact | Promise<Artifact>;
}

const NAME = /^[a-z][a-z0-9_-]*$/u;

function decls(options: Record<string, OptionSpec> | undefined): OptionDecl[] {
  return Object.entries(options ?? {}).map(([name, spec]) => ({
    name,
    type: spec.type,
    aliases: [...(spec.aliases ?? [])],
    param: null,
    default: spec.default ?? null,
    help: spec.help ?? "",
    example: spec.example ?? "",
  }));
}

/**
 * Register a processor of your own.
 *
 * @example
 * processor({
 *   extensions: [".pdf"],
 *   name: "invoice",
 *   detect: (data, filename) => filename.startsWith("INV-"),
 *   options: { currency: { type: "str", default: "EUR", help: "Currency of the totals" } },
 *   async process(data, { currency }, { base }) {
 *     const standard = await base();
 *     return makeArtifact({ text: `${currency}\n${standard.text}` });
 *   },
 * });
 */
export function processor<O extends Record<string, OptionSpec> = Record<never, OptionSpec>>(spec: ProcessorSpec<O>): void {
  const fn = spec.process as unknown as ProcessorFn;
  if (spec.name === undefined) {
    if (spec.detect !== undefined) throw new TypeError("detect needs a name (it chooses a named processor)");
    for (const ext of spec.extensions) {
      processors.set(normalizeKey(ext), fn);
      if (spec.options !== undefined) registerOptions(ext, decls(spec.options));
    }
    return;
  }
  if (!NAME.test(spec.name) || spec.name === STANDARD) {
    throw new TypeError(`processor name must be lowercase letters, digits, '-' or '_' (and not '${STANDARD}'), got '${spec.name}'`);
  }
  if (spec.extensions.length === 0) throw new TypeError("a named processor needs at least one extension");
  const entry = { name: spec.name, fn, detect: spec.detect ?? null, options: decls(spec.options) };
  for (const ext of spec.extensions) {
    const key = normalizeKey(ext);
    const table = namedProcessors.get(key) ?? new Map();
    table.delete(spec.name); // registering again moves it to the end
    table.set(spec.name, entry);
    namedProcessors.set(key, table);
  }
}

/**
 * Register a source: inputs starting with one of its prefixes are read
 * by it.
 *
 * @example
 * source({ prefixes: ["s3://"], async unpack(input) { return [new File([await get(input)], key(input))]; } });
 */
export function source(spec: SourceSpec): void {
  for (const prefix of spec.prefixes) sources.set(prefix, spec);
}
