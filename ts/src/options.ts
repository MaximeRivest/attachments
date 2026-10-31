/**
 * Options belong to processors and sources: each declares its own
 * (contract/dsl-schema.json). Resolution matches raw options from the
 * string and from the call against a declaration, coerces each value to
 * its type, and drops what does not fit with a warning that says why
 * (contract/presenting.md, "Options").
 */

import { closeMatch } from "./difflib.ts";
import { type DslValue, Written } from "./dsl.ts";
import { PROCESSOR_OPTIONS, SOURCE_OPTIONS } from "./generated/schema.ts";
import { PageSelection, PageSelectionError, parsePages } from "./pages.ts";
import { pyRepr, strip } from "./text.ts";

export type OptionType = "str" | "int" | "float" | "bool" | "pages" | "bool_or_auto" | "str_or_int";

/** One declared option (the shape of `dsl-schema.json`). */
export interface OptionDecl {
  /** The contract name: in the string, in `att()`'s options, in warnings. */
  name: string;
  type: OptionType | (string & {});
  aliases: readonly string[];
  /** Python's parameter name; accepted as a hidden alias. */
  param: string | null;
  default: unknown;
  help: string;
  example: string;
}

/** A coerced value: pages become a {@link PageSelection}. */
export type OptionValue = string | number | boolean | PageSelection;

const BOOL: Record<string, boolean> = { true: true, yes: true, on: true, false: false, no: false, off: false };

class Mismatch extends Error {}

const isRange = (v: unknown): v is readonly [number, number] =>
  Array.isArray(v) && v.length === 2 && v.every((x) => typeof x === "number" && Number.isInteger(x));

function coerce(decl: OptionDecl, value: unknown): OptionValue {
  switch (decl.type) {
    case "pages":
      try {
        return parsePages(value);
      } catch (e) {
        if (e instanceof PageSelectionError) {
          throw new Mismatch(
            "a 1-based page (3), a range (2-5, 7-), a list (1,3,5) or pages counted from the end (-1 = last, -3- = last three)",
          );
        }
        throw e;
      }
    case "str":
      if (typeof value === "boolean") return value ? "true" : "false";
      if (isRange(value)) return `${value[0]}-${value[1]}`;
      return typeof value === "string" ? value : String(value);
    case "int":
      if (typeof value === "number" && Number.isInteger(value)) return value;
      if (typeof value === "string" && /^-?[0-9]+$/u.test(strip(value))) return Number(strip(value));
      throw new Mismatch("an integer");
    case "float":
      if (typeof value === "number") return value;
      if (typeof value === "string" && strip(value) !== "" && Number.isFinite(Number(value))) return Number(value);
      throw new Mismatch("a number");
    case "bool":
      if (typeof value === "boolean") return value;
      if (typeof value === "string" && strip(value).toLowerCase() in BOOL) return BOOL[strip(value).toLowerCase()]!;
      throw new Mismatch("a boolean (true/false)");
    case "bool_or_auto": {
      if (typeof value === "boolean") return value;
      if (typeof value === "string") {
        const lowered = strip(value).toLowerCase();
        if (lowered === "auto" || lowered === "always") return lowered;
        if (lowered in BOOL) return BOOL[lowered]!;
      }
      throw new Mismatch("a boolean, 'auto', or 'always'");
    }
    case "str_or_int":
      if (typeof value === "string" || (typeof value === "number" && Number.isInteger(value))) return value;
      throw new Mismatch("a string or integer");
    default:
      throw new Mismatch(`a value of type '${decl.type}'`);
  }
}

function show(value: unknown): string {
  return value instanceof PageSelection ? String(value) : pyRepr(value);
}

/** The result of resolving raw options against declarations. */
export interface Resolved {
  /** Coerced values by contract name, in the order given. */
  options: Record<string, OptionValue>;
  /** One sentence per option dropped. */
  warnings: string[];
}

/**
 * Resolve raw options (the string's, then the call's: later keys win)
 * against `decls`. Never throws: what does not fit is dropped with a
 * warning.
 */
export function resolveOptions(
  decls: readonly OptionDecl[],
  raw: Readonly<Record<string, DslValue | unknown>>,
  context: string,
): Resolved {
  const lookup = new Map<string, OptionDecl>();
  for (const d of decls) {
    if (!lookup.has(d.name)) lookup.set(d.name, d);
    for (const alias of d.aliases) if (!lookup.has(alias)) lookup.set(alias, d);
    if (d.param && !lookup.has(d.param)) lookup.set(d.param, d);
  }
  const bySpelling = new Map<string, OptionDecl>(decls.map((d) => [d.name, d]));
  for (const d of decls) for (const alias of d.aliases) if (!bySpelling.has(alias)) bySpelling.set(alias, d);
  const suggestible = [...bySpelling.keys()].sort();

  const options: Record<string, OptionValue> = {};
  const warnings: string[] = [];
  for (const [key, given] of Object.entries(raw)) {
    const decl = lookup.get(key);
    const value = decl ? writtenValue(decl, given) : given;
    if (decl === undefined) {
      let message = `Unknown option '${key}' for ${context}`;
      const close = closeMatch(key, suggestible);
      if (close !== null) {
        const meant = bySpelling.get(close)!;
        message += ` — did you mean '${meant.name}'?`;
        if (meant.example) message += ` (e.g. [${meant.example}])`;
      }
      warnings.push(message);
      continue;
    }
    try {
      options[decl.name] = coerce(decl, value);
    } catch (e) {
      if (!(e instanceof Mismatch)) throw e;
      let message = `Invalid value for option '${decl.name}' on ${context}: expected ${e.message}, got ${show(value)}`;
      if (decl.example) message += ` (e.g. [${decl.example}])`;
      warnings.push(message);
    }
  }
  return { options, warnings };
}

/** The value an option takes from a {@link Written}: `str` the text, other types the value. */
export function writtenValue(decl: OptionDecl, value: unknown): unknown {
  if (value instanceof Written) return decl.type === "str" ? value.text : value.value;
  return value;
}

/** Raw options for the service: written values unwrapped by their declaration (unknown keys typed). */
export function plainOptions(decls: readonly OptionDecl[], raw: Readonly<Record<string, unknown>>): Record<string, unknown> {
  const lookup = new Map<string, OptionDecl>();
  for (const d of decls) for (const n of [d.name, ...d.aliases, d.param]) if (n && !lookup.has(n)) lookup.set(n, d);
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(raw)) {
    const d = lookup.get(k);
    out[k] = v instanceof Written ? (d ? writtenValue(d, v) : v.value) : v;
  }
  return out;
}

const registered = new Map<string, readonly OptionDecl[]>();

/** Declare the options of a processor key or source prefix (processors of your own). @internal */
export function registerOptions(key: string, decls: readonly OptionDecl[]): void {
  registered.set(normalizeOptionKey(key), decls);
}

function normalizeOptionKey(key: string): string {
  let k = strip(key);
  if (k.includes("://") || k.startsWith("__")) return k;
  if (!k.startsWith(".")) k = `.${k}`;
  return k.toLowerCase();
}

/** Every declared option, by key: the contract's, then those registered here. */
export function allDeclared(): { processors: Record<string, readonly OptionDecl[]>; sources: Record<string, readonly OptionDecl[]> } {
  const processors: Record<string, readonly OptionDecl[]> = { ...PROCESSOR_OPTIONS };
  const sources: Record<string, readonly OptionDecl[]> = { ...SOURCE_OPTIONS };
  for (const [k, v] of registered) (k.includes("://") ? sources : processors)[k] = v;
  return { processors, sources };
}

/** The declared options of a processor key (`.pdf`, `pdf`) or a source prefix (`github://`). */
export function declaredOptions(key: string): readonly OptionDecl[] {
  const k = normalizeOptionKey(key);
  return registered.get(k) ?? (k.includes("://") ? SOURCE_OPTIONS[k] : PROCESSOR_OPTIONS[k]) ?? [];
}
