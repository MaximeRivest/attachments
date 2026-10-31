/**
 * TypeScript against the contract's cases (`contract/cases/*.json`), the
 * same files Python's `tests/test_contract_cases.py` reads. Arguments in
 * the cases use the contract's names (`max_chars`); this driver maps them
 * to TypeScript's (`maxChars`).
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, test } from "node:test";
import { fileURLToPath } from "node:url";

import { AttachmentsError, Artifacts } from "attachments-dev";
import { declaredOptions, formatDsl, imageTokens, parseDsl, parsePages, PageSelection, resolveOptions } from "attachments-dev/extend";
import { decodeStrict } from "../src/base64.ts";
import { imageSize } from "../src/imagesize.ts";
import { CLAUDE, OPENAI, requestProblems } from "../src/limits.ts";
import { captureWarnings } from "../src/warn.ts";

const CASES = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "contract", "cases");

type Case = Record<string, any>;

function load(area: string): Case[] {
  return JSON.parse(readFileSync(join(CASES, `${area}.json`), "utf8")).cases;
}

const expand = (v: any): any => (v && typeof v === "object" && "repeat" in v ? v.repeat.repeat(v.times) : v);

function artifacts(c: Case): Artifacts {
  return Artifacts.fromWire(c.artifacts.map((a: any) => ({ ...a, text: expand(a.text) })));
}

const camel = (k: string): string => k.replace(/_([a-z])/g, (_, ch: string) => ch.toUpperCase());
const camelArgs = (args: Record<string, unknown> = {}): Record<string, any> =>
  Object.fromEntries(Object.entries(args).map(([k, v]) => [camel(k), v]));

function warningKinds(ws: { type: string }[]): string[] {
  return ws.map((w) => (w.type === "RequestLimitWarning" ? "request-limit" : w.type === "AttachmentsWarning" ? "named-labels" : `other: ${w.type}`));
}

function present(c: Case): unknown {
  const a = artifacts(c);
  const { prompt, ...rest } = camelArgs(c.args);
  let result;
  try {
    result = captureWarnings(() => {
      switch (c.call) {
        case "text":
          return a.toText(rest);
        case "parts":
          return a.parts({ ...rest, prompt });
        case "claude":
          return a.claude(prompt, rest);
        case "openai":
          return a.openai(prompt, rest);
        case "lm15": {
          const m = a.lm15(prompt, rest);
          return {
            role: m.role,
            parts: m.parts.map((p) => (p.type === "text" ? { type: "text", text: p.text } : { type: "image", media_type: p.mediaType, data: p.data })),
          };
        }
      }
      throw new Error(c.call);
    });
  } catch (e) {
    if (e instanceof RangeError) return { throws: true };
    throw e;
  }
  const out: Record<string, unknown> = { value: result.value };
  if (result.warnings.length > 0) out["warnings"] = warningKinds(result.warnings);
  return out;
}

function throwsOr(fn: () => unknown): unknown {
  try {
    return { value: fn() };
  } catch (e) {
    if (e instanceof RangeError || e instanceof TypeError || e instanceof SyntaxError) return { throws: true };
    throw e;
  }
}

/** Plain JSON values, so deepEqual compares data and not classes. */
const plain = (v: unknown): unknown => JSON.parse(JSON.stringify(v));

const AREAS: Record<string, (c: Case) => unknown> = {
  present,
  chunk: (c) => throwsOr(() => artifacts(c).chunk(camelArgs(c.args))),
  tokens: (c) =>
    throwsOr(() =>
      c.call === "estimate" ? artifacts(c).estimateTokens(camelArgs(c.args)) : imageTokens(c.width, c.height, { tier: c.tier }),
    ),
  imagesize: (c) => ({ value: imageSize(decodeStrict(c.bytes_b64)!) }),
  limits: (c) => ({
    value: requestProblems(
      c.parts.map((p: any) => ({ ...p, data: expand(p.data), text: expand(p.text) })),
      c.provider === "claude" ? CLAUDE : OPENAI,
    ),
  }),
  wire: (c) =>
    throwsOr(() => (c.call === "from_wire" ? Artifacts.fromWire(c.input).toWire() : Artifacts.fromWire([c.input]).toWire()[0])),
  dsl: (c) => {
    const text = formatDsl(c.source, c.options);
    const [source, options] = parseDsl(text);
    return { value: text, reparsed: { source, options } };
  },
  pages: (c) => {
    let selection: PageSelection;
    try {
      selection = parsePages(c.value);
    } catch {
      return { throws: true };
    }
    const out: Record<string, unknown> = { text: String(selection) };
    if ("total" in c) out["indices"] = selection.pages(c.total);
    return out;
  },
  options: (c) => {
    const { options, warnings } = resolveOptions(declaredOptions(c.key), c.raw, c.key);
    const unknown: unknown[] = [];
    const invalid: string[] = [];
    for (const w of warnings) {
      let m = /^Unknown option '(.*?)' for .*? — did you mean '(.*?)'\?/u.exec(w);
      if (m) unknown.push({ key: m[1], suggest: m[2] });
      else if ((m = /^Unknown option '(.*?)' for /u.exec(w))) unknown.push({ key: m[1], suggest: null });
      else if ((m = /^Invalid value for option '(.*?)' on /u.exec(w))) invalid.push(m[1]!);
      else throw new Error(w);
    }
    return { resolved: plain(options), unknown, invalid };
  },
  summary: (c) => {
    const a = artifacts(c);
    let error_message: string | null = null;
    try {
      a.throwIfErrors();
    } catch (e) {
      assert.ok(e instanceof AttachmentsError);
      error_message = e.message;
    }
    return { repr: (a as any)[Symbol.for("nodejs.util.inspect.custom")](), errors: a.errors, error_message };
  },
};

for (const [area, run] of Object.entries(AREAS)) {
  describe(area, () => {
    for (const c of load(area)) {
      test(c.name, () => {
        assert.deepEqual(plain(run(c)), c.expect);
      });
    }
  });
}
