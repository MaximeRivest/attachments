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
