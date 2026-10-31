/**
 * TypeScript's client against Python's server: every format TypeScript
 * leaves to the service, read by a real `python -m attachments.server`,
 * must give what Python gives reading the file itself (with
 * `meta.via = "service"`). Skipped when the Python environment (`../.venv`)
 * is missing.
 */

import assert from "node:assert/strict";
import { execFileSync, spawn, type ChildProcess } from "node:child_process";
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { createServer } from "node:net";
import { dirname, join } from "node:path";
import { after, before, describe, test } from "node:test";
import { fileURLToPath } from "node:url";

import { att } from "attachments-dev";

const repo = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const python = join(repo, ".venv", "bin", "python");
const files = join(repo, "tests", "extras", "files");
const skip = !existsSync(python) ? "no ../.venv (run uv sync in the repository)" : false;

async function freePort(): Promise<number> {
  return new Promise((resolve) => {
    const s = createServer().listen(0, "127.0.0.1", () => {
      const port = (s.address() as { port: number }).port;
      s.close(() => resolve(port));
    });
  });
}

/** Python's own reading of each file, in wire form. */
function pythonReads(names: string[]): Record<string, unknown[]> {
  const script = `
import json, sys
from attachments import att
out = {n: att(sys.argv[1] + "/" + n, prefer="local-only").to_wire() for n in sys.argv[2:]}
print(json.dumps(out))`;
  const env = Object.fromEntries(Object.entries(process.env).filter(([k]) => !k.startsWith("ATTACHMENTS_")));
  return JSON.parse(execFileSync(python, ["-c", script, files, ...names], { env, maxBuffer: 256 * 1024 * 1024 }).toString());
}

/** Python's reading of files given as `{ name, b64 }`, error messages left out. */
function pythonReadsBytes(files: { name: string; b64: string }[]): unknown[] {
  const script = `
import base64, io, json, sys, warnings, logging
logging.disable(logging.CRITICAL)
warnings.simplefilter("ignore")
from attachments import att
out = []
for f in json.load(sys.stdin):
    b = io.BytesIO(base64.b64decode(f["b64"])); b.name = f["name"]
    wire = att(b, prefer="local-only").to_wire()
    for a in wire:
        if "error" in a["meta"]: a["meta"]["error"] = {"code": a["meta"]["error"]["code"]}
    out.append(wire)
# NaN is not JSON: written as null, as JSON.stringify writes it.
print(json.dumps(json.loads(json.dumps(out), parse_constant=lambda c: None)))`;
  const env = Object.fromEntries(Object.entries(process.env).filter(([k]) => !k.startsWith("ATTACHMENTS_")));
  return JSON.parse(execFileSync(python, ["-c", script], { env, input: JSON.stringify(files), maxBuffer: 256 * 1024 * 1024 }).toString());
}

/** A seeded generator, so a failure can be replayed. */
function random(seed: number): () => number {
  let s = seed >>> 0;
  return () => {
    s = (s + 0x6d2b79f5) >>> 0;
    let t = Math.imul(s ^ (s >>> 15), 1 | s);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

describe("TypeScript and Python read the same bytes the same way", { skip }, () => {
  test("random CSV and mutated SVG and notebooks", async () => {
    const rnd = random(Number(process.env["ATT_FUZZ_SEED"] ?? 2026));
    const pick = <T>(list: readonly T[]): T => list[Math.floor(rnd() * list.length)]!;
    const files: { name: string; data: Uint8Array }[] = [];
    const csvAtoms = ["a", "b", "1", "22", ",", ",", ";", "\t", "|", '"', "'", " ", "\n", "\n", "\r\n", "é", "x y", '""'];
    for (let i = 0; i < 400; i++) {
      let text = "";
      const n = Math.floor(rnd() * 60);
      for (let j = 0; j < n; j++) text += pick(csvAtoms);
      files.push({ name: pick(["r.csv", "r.tsv"]), data: new TextEncoder().encode(text) });
    }
    // Long, mostly regular tables: the guesser reads in blocks of ten lines.
    for (let i = 0; i < 200; i++) {
      const delims = [",", ";", "\t", "|", " ", ":"];
      const main = pick(delims);
      const lines: string[] = [];
      const width = 1 + Math.floor(rnd() * 4);
      for (let r = 0; r < 5 + Math.floor(rnd() * 60); r++) {
        const sep = rnd() < 0.9 ? main : pick(delims);
        const cells = Array.from({ length: rnd() < 0.9 ? width : 1 + Math.floor(rnd() * 5) }, () =>
          rnd() < 0.2 ? `"${pick(["a", "b,c", 'd""e', "f\ng"])}"` : pick(["x", "12", "3.5", "", "é", "a b"]),
        );
        lines.push(cells.join(sep));
      }
      files.push({ name: "long.csv", data: new TextEncoder().encode(lines.join(rnd() < 0.8 ? "\n" : "\r\n")) });
    }
    const svgs = [
      '<svg xmlns="http://www.w3.org/2000/svg" width="1" viewBox="0 0 1 1"><title>T</title><text x="1">a<tspan>b</tspan>c</text></svg>',
      '<?xml version="1.0"?><!DOCTYPE svg [<!ENTITY e "x &amp; y">]><svg><text>&e; &#233;<!-- c --> z</text></svg>',
      '<s:svg xmlns:s="u"><s:desc>d</s:desc><g><![CDATA[q]]></g></s:svg>',
    ];
    const svgAtoms = ["<", ">", "/", "&", ";", '"', "'", "=", " ", "\n", "a", "text", "<!--", "-->", "&amp;", "&e;", ":", "]]>", "<![CDATA["];
    for (let i = 0; i < Number(process.env["ATT_FUZZ_SVGS"] ?? 400); i++) {
      let text = pick(svgs);
      const edits = 1 + Math.floor(rnd() * 3);
      for (let j = 0; j < edits; j++) {
        const at = Math.floor(rnd() * (text.length + 1));
        const cut = rnd() < 0.5 ? Math.floor(rnd() * 4) : 0;
        text = text.slice(0, at) + (rnd() < 0.7 ? pick(svgAtoms) : "") + text.slice(at + cut);
      }
      files.push({ name: "d.svg", data: new TextEncoder().encode(text) });
    }
    const nbAtoms = ['{"cells": [', '{"cell_type": "code", "source": ["x\\n", 1.0]}', "]", "}", ",", '"metadata": {"language_info": {"name": "r"}}', "NaN", "null", '"outputs": [{"output_type": "stream", "text": "o"}]'];
    for (let i = 0; i < 200; i++) {
      let text = '{"cells": [{"cell_type": "markdown", "source": "m"}, {"cell_type": "code", "source": "c", "outputs": []}], "nbformat": 4}';
      const edits = Math.floor(rnd() * 3);
      for (let j = 0; j < edits; j++) {
        const at = Math.floor(rnd() * (text.length + 1));
        text = text.slice(0, at) + pick(nbAtoms) + text.slice(at + Math.floor(rnd() * 3));
      }
      files.push({ name: "n.ipynb", data: new TextEncoder().encode(text) });
    }
    const expected = pythonReadsBytes(files.map((f) => ({ name: f.name, b64: Buffer.from(f.data).toString("base64") })));
    const local = att.with({ prefer: "local-only" });
    let differ = 0;
    for (const [i, f] of files.entries()) {
      const got = JSON.parse(JSON.stringify(await local(new File([f.data as BlobPart], f.name)))).map((a: any) => {
        if (a.meta.error) a.meta.error = { code: a.meta.error.code };
        return a;
      });
      try {
        assert.deepEqual(got, expected[i]);
      } catch (err) {
        differ++;
        if (differ <= 5) console.error(f.name, JSON.stringify(new TextDecoder().decode(f.data)), (err as Error).message.slice(0, 1500));
      }
    }
    assert.equal(differ, 0, `${differ} of ${files.length} files read differently`);
  });
});

describe("TypeScript client, Python server", { skip }, () => {
  let server: ChildProcess;
  let url = "";
  const names = skip ? [] : readdirSync(files).sort();

  before(async () => {
    const port = await freePort();
    url = `http://127.0.0.1:${port}`;
    const env = Object.fromEntries(Object.entries(process.env).filter(([k]) => !k.startsWith("ATTACHMENTS_")));
    server = spawn(python, ["-m", "attachments.server", "--host", "127.0.0.1", "--port", String(port)], { env, stdio: "ignore" });
    for (let i = 0; i < 100; i++) {
      try {
        if ((await fetch(`${url}/health`)).ok) return;
      } catch {
        /* not up yet */
      }
      await new Promise((r) => setTimeout(r, 100));
    }
    throw new Error("the Python server did not start");
  });
  after(() => server?.kill());

  test("every file: the service's answer is Python's reading", async () => {
    const expected = pythonReads(names);
    const service = att.with({ serviceUrl: url, prefer: "service-only" });
    for (const name of names) {
      const got = JSON.parse(JSON.stringify(await service(new File([readFileSync(join(files, name))], name))));
      const want = (expected[name] as { meta: Record<string, unknown> }[]).map((a) => ({ ...a, meta: { ...a.meta, via: "service" } }));
      assert.deepEqual(got, want, name);
    }
  });

  test("the default mode reads text here and the rest there", async () => {
    const both = att.with({ serviceUrl: url });
    const a = await both([new File(["# notes"], "n.md"), new File([readFileSync(join(files, "report.docx"))], "report.docx")]);
    assert.deepEqual(a.map((x) => x.meta.via ?? "here"), ["here", "service"]);
  });

  test("options reach the server: pages of a PDF", async () => {
    const service = att.with({ serviceUrl: url, prefer: "service-only" });
    const pdf = new File([readFileSync(join(files, "text.pdf"))], "text.pdf");
    const [one] = await service(pdf, { pages: "1" });
    const [all] = await service(pdf);
    assert.ok(one!.text.length > 0 && one!.text.length <= all!.text.length);
  });
});
