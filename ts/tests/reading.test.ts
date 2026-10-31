/**
 * TypeScript against the reading cases (contract/reading.md), the same
 * files Python's `tests/_contract_reading.py` answers. Artifacts are
 * compared in wire form without error messages.
 */

import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, readFileSync, symlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { describe, test } from "node:test";
import { fileURLToPath } from "node:url";

import { att, type WireArtifact } from "attachments-dev";
import { findMentions } from "../src/mentions.ts";
import { detectExtension, isTextBytes, textProcessor } from "../src/processors.ts";
import { compileRules, decide, IgnoreEngine, looksLikeKey } from "../src/sources/ignore.ts";
import { looksLikeGlob, patternRegex, splitPattern } from "../src/sources/tree.ts";
import { captureWarnings } from "../src/warn.ts";

const CASES = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "contract", "cases");
/** What this implementation has of the contract's declared extensions. */
const EXTENSIONS = new Set<string>();

for (const k of Object.keys(process.env)) if (k.startsWith("ATTACHMENTS_")) delete process.env[k];

type Case = Record<string, any>;
const load = (area: string): { cases: Case[]; fixtures?: Record<string, Record<string, any>> } =>
  JSON.parse(readFileSync(join(CASES, `${area}.json`), "utf8"));

const bytes = (b64: string): Uint8Array<ArrayBuffer> => Uint8Array.from(Buffer.from(b64, "base64"));

function normalize(artifacts: readonly unknown[]): unknown {
  return JSON.parse(JSON.stringify(artifacts)).map((a: WireArtifact) => {
    if (a.meta?.error) a.meta.error = { code: a.meta.error.code } as never;
    return a;
  });
}

function input(spec: any): unknown {
  if (Array.isArray(spec)) return spec.map(input);
  if (typeof spec === "string") return spec;
  if ("bytes_b64" in spec) {
    const data = bytes(spec.bytes_b64);
    return spec.name === null ? new Blob([data]) : new File([data], spec.name);
  }
  if ("bare_bytes_b64" in spec) return bytes(spec.bare_bytes_b64);
  if ("number" in spec) return spec.number;
  throw new Error(JSON.stringify(spec));
}

async function runAtt(c: Case): Promise<unknown> {
  const { value } = captureWarnings(() => att(input(c.input) as never, { prefer: "local-only", ...(c.options ?? {}) }));
  return { artifacts: normalize(await value) };
}

const fixtureRoots = new Map<string, string>();
function fixture(name: string, files: Record<string, any>): string {
  let root = fixtureRoots.get(name);
  if (root === undefined) {
    root = mkdtempSync(join(tmpdir(), "attachments-contract-"));
    for (const [rel, spec] of Object.entries(files)) {
      const path = join(root, rel);
      mkdirSync(dirname(path), { recursive: true });
      if (typeof spec === "string") writeFileSync(path, spec);
      else if ("b64" in spec) writeFileSync(path, bytes(spec.b64));
      else if ("link" in spec) symlinkSync(spec.link, path);
      else if (spec.dir) mkdirSync(path, { recursive: true });
    }
    fixtureRoots.set(name, root);
  }
  return root;
}

const AREAS: Record<string, (c: Case, doc: ReturnType<typeof load>) => Promise<unknown> | unknown> = {
  inputs: runAtt,
  archives: runAtt,
  async trees(c, doc) {
    const previous = process.cwd();
    process.chdir(fixture(c.fixture, doc.fixtures![c.fixture]!));
    try {
      return await runAtt(c);
    } finally {
      process.chdir(previous);
    }
  },
  async ignore(c) {
    if (c.call === "decide") return { value: decide(compileRules(c.patterns), c.path, c.is_dir) };
    if (c.call === "check") {
      const e = c.engine;
      return { value: await new IgnoreEngine({ extra: e.extra ?? [], defaults: e.defaults ?? true, hidden: e.hidden ?? false }).check(c.path, c.is_dir) };
    }
    return { value: looksLikeKey(bytes(c.bytes_b64)) };
  },
  globs(c) {
    if (c.call === "split") return { value: splitPattern(c.pattern) };
    if (c.call === "match") return { value: patternRegex(c.components, c.hidden).test(c.path) };
    return { value: looksLikeGlob(c.text) };
  },
  async text(c) {
    const data = bytes(c.bytes_b64);
    if (c.call === "text") {
      const a = await textProcessor(data, {}, { filename: "t.txt", base: () => Promise.reject(new Error()) });
      return { value: { text: a.text, meta: a.meta } };
    }
    if (c.call === "sniff") return { value: detectExtension(data) };
    return { value: isTextBytes(data) };
  },
  mentions: (c) => ({ value: findMentions(c.prompt).map(({ text, explicit, url }) => ({ text, explicit, url })) }),
};

for (const [area, run] of Object.entries(AREAS)) {
  const doc = load(area);
  describe(area, () => {
    for (const c of doc.cases) {
      const missing = (c.requires ?? []).filter((r: string) => !EXTENSIONS.has(r));
      if (missing.length > 0) {
        test(`${c.name} (without ${missing.join(", ")}: refused)`, async () => {
          const { artifacts } = (await runAtt(c)) as { artifacts: WireArtifact[] };
          assert.ok(artifacts.length > 0 && artifacts.every((a) => a.meta.error?.code === "unpack-error"), JSON.stringify(artifacts));
        });
        continue;
      }
      test(c.name, async () => {
        assert.deepEqual(JSON.parse(JSON.stringify(await run(c, doc))), c.expect);
      });
    }
  });
}

// -- routing, downloads, naming ------------------------------------------------------

import { createServer, type IncomingMessage, type Server } from "node:http";
import { configure } from "attachments-dev";
import { resetConfig } from "../src/config.ts";
import { registerOptions } from "../src/options.ts";
import { processors, type ProcessorFn } from "../src/processors.ts";
import { filenameFromContentDisposition, githubRawUrl, nameForContentType } from "../src/sources/download.ts";
import { sanitizeMemberName } from "../src/sources/archives.ts";
import { makeArtifact, errorArtifact } from "attachments-dev/extend";

interface Scripted {
  base: string;
  requests: unknown[];
  close(): Promise<void>;
}

async function scripted(answer: (req: IncomingMessage, body: Buffer) => [number, Record<string, string>, Buffer]): Promise<Scripted> {
  const requests: unknown[] = [];
  const server: Server = createServer((req, res) => {
    const chunks: Buffer[] = [];
    req.on("data", (c: Buffer) => chunks.push(c));
    req.on("end", () => {
      const [status, headers, payload] = answer(req, Buffer.concat(chunks));
      res.writeHead(status, { ...headers, "Content-Length": String(payload.length) });
      res.end(payload);
    });
  });
  await new Promise<void>((r) => server.listen(0, "127.0.0.1", r));
  const port = (server.address() as { port: number }).port;
  return {
    base: `http://127.0.0.1:${port}`,
    requests,
    close: () => new Promise<void>((r) => server.close(() => r())),
  };
}

function parseMultipart(type: string, body: Buffer): Record<string, unknown> {
  const boundary = type.split("boundary=")[1]!.replace(/^"|"$/gu, "");
  const out: Record<string, any> = { filename: null, fields: {}, file_b64: null };
  for (const raw of body.toString("latin1").split(`--${boundary}`)) {
    const at = raw.indexOf("\r\n\r\n");
    if (at === -1) continue;
    const head = Buffer.from(raw.slice(0, at), "latin1").toString("utf8");
    let content = raw.slice(at + 4);
    if (content.endsWith("\r\n")) content = content.slice(0, -2);
    if (head.includes('filename="')) {
      const s = head.indexOf('filename="') + 10;
      out["filename"] = head.slice(s, head.indexOf('"', s));
      out["file_b64"] = Buffer.from(content, "latin1").toString("base64");
    } else if (head.includes('name="')) {
      const s = head.indexOf('name="') + 6;
      out["fields"][head.slice(s, head.indexOf('"', s))] = JSON.parse(Buffer.from(content, "latin1").toString("utf8"));
    }
  }
  return out;
}

async function fakeService(answers: any[]): Promise<Scripted> {
  const queue = [...answers];
  const service: Scripted = await scripted((req, body) => {
    service.requests.push({
      method: req.method,
      path: req.url,
      auth: req.headers.authorization ?? null,
      ...parseMultipart(String(req.headers["content-type"] ?? ""), body),
    });
    const reply = queue.shift() ?? { status: 500, json: { error: "no answer left" } };
    return [reply.status, { "Content-Type": "application/json" }, Buffer.from("json" in reply ? JSON.stringify(reply.json) : reply.body)];
  });
  return service;
}

function fakeProcessor(behavior: string): ProcessorFn {
  return (data, options, { filename }) => {
    if (behavior === "text") {
      const extra = Object.fromEntries(["password", "dpi"].filter((k) => k in options).map((k) => [k, options[k]]));
      return makeArtifact({ text: new TextDecoder().decode(data), meta: { kind: "text", ...(Object.keys(extra).length ? { extra } : {}) } });
    }
    if (behavior === "missing") return errorArtifact(filename, "missing-dependency", "the fake reader is missing");
    if (behavior === "partial") {
      return makeArtifact({ text: "partial text", meta: { extra: { missing_dependency: "image" }, warnings: ["pictures not made"] } });
    }
    if (behavior === "parse-error") return errorArtifact(filename, "parse-error", "bad");
    if (behavior === "throw") throw new Error("boom");
    if (behavior === "missing-module") throw Object.assign(new Error("Cannot find package 'fakelib'"), { code: "ERR_MODULE_NOT_FOUND" });
    throw new Error(behavior);
  };
}

const replaceBase = (value: unknown, base: string): unknown => JSON.parse(JSON.stringify(value).replaceAll(base, "http://HOST"));

const NETWORK: Record<string, (c: Case, doc: any) => Promise<unknown> | unknown> = {
  async routing(c, doc) {
    const root = mkdtempSync(join(tmpdir(), "attachments-routing-"));
    const previousProcessor = processors.get(".fake");
    processors.set(".fake", fakeProcessor(c.behavior));
    registerOptions(".fake", doc.fake_options);
    const service = c.service ? await fakeService(c.service.answers) : null;
    const previous = process.cwd();
    process.chdir(root);
    try {
      resetConfig();
      configure({
        ...(service ? { serviceUrl: service.base + (c.service.v1 ? "/v1" : "") } : {}),
        ...(c.api_key ? { apiKey: c.api_key } : {}),
      });
      let given: unknown;
      if ("text" in c.input) {
        writeFileSync(join(root, c.input.file), bytes(c.input.bytes_b64));
        given = c.input.text;
      } else given = input(c.input);
      const { value } = captureWarnings(() => att(given as never, { prefer: c.prefer, ...c.options }));
      return { artifacts: normalize(await value), requests: service?.requests ?? [] };
    } finally {
      process.chdir(previous);
      resetConfig();
      await service?.close();
      if (previousProcessor) processors.set(".fake", previousProcessor);
      else processors.delete(".fake");
    }
  },
  async downloads(c, doc) {
    const web = await scripted((req) => {
      const route = doc.routes[req.url!] ?? { status: 404, body: "no route" };
      return [route.status, route.headers ?? {}, "body_b64" in route ? Buffer.from(route.body_b64, "base64") : Buffer.from(route.body ?? "")];
    });
    try {
      const reader = c.block_private ? att.with({ blockPrivateUrls: true }) : att;
      const { value } = captureWarnings(() => reader(web.base + c.path, { prefer: "local-only", ...c.options }));
      return { artifacts: replaceBase(normalize(await value), web.base) };
    } finally {
      await web.close();
    }
  },
  naming(c) {
    if (c.call === "disposition") return { value: filenameFromContentDisposition(c.value) };
    if (c.call === "type") return { value: nameForContentType(c.filename, c.content_type, c.url) };
    if (c.call === "raw") return { value: githubRawUrl(c.url) };
    return { value: sanitizeMemberName(c.value) };
  },
};

for (const [area, run] of Object.entries(NETWORK)) {
  const doc = load(area);
  describe(area, () => {
    for (const c of doc.cases) {
      test(c.name, async () => {
        assert.deepEqual(JSON.parse(JSON.stringify(await run(c, doc))), c.expect);
      });
    }
  });
}
