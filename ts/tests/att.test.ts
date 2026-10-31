/** `att()` as TypeScript code uses it. */

import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { after, before, test } from "node:test";

import { att, AttachmentsError, Artifacts, checkDeps, configure } from "attachments-dev";
import { makeArtifact, processor, source } from "attachments-dev/extend";
import { PENDING_GETTERS, PENDING_METHODS } from "../src/att.ts";
import { resetConfig } from "../src/config.ts";
import { captureWarnings } from "../src/warn.ts";

let root = "";
const previous = process.cwd();
before(() => {
  root = mkdtempSync(join(tmpdir(), "attachments-att-"));
  mkdirSync(join(root, "docs"));
  writeFileSync(join(root, "docs", "a.md"), "# A\n");
  writeFileSync(join(root, "docs", "b.txt"), "bee");
  writeFileSync(join(root, "notes.txt"), "plain notes");
  process.chdir(root);
});
after(() => process.chdir(previous));

test("a pending result has every method and getter of Artifacts", () => {
  const own = Object.getOwnPropertyNames(Artifacts.prototype).filter(
    (n) => !["constructor", "filter", "slice", "concat", "toJSON", "toString", "throwIfErrors"].includes(n),
  );
  assert.deepEqual([...own].sort(), [...PENDING_METHODS, ...PENDING_GETTERS].sort());
});

test("await gives Artifacts; methods work on the pending result", async () => {
  const a = await att("notes.txt");
  assert.ok(a instanceof Artifacts);
  assert.equal(await att("notes.txt").text, "## notes.txt\nplain notes");
  const messages = await att("notes.txt").claude("Summarize.");
  assert.deepEqual(messages[0]!.content.at(-1), { type: "text", text: "Summarize." });
  assert.equal((await att("notes.txt").chunk({ maxChars: 5, overlap: 0 })).length, 3);
});

test("throwIfErrors chains, and rejects with every failure", async () => {
  assert.equal((await att("notes.txt").throwIfErrors().parts()).length, 1);
  await assert.rejects(att(["notes.txt", "missing.txt"]).throwIfErrors().claude("Q"), (e: unknown) => {
    assert.ok(e instanceof AttachmentsError);
    assert.equal(e.errors.length, 1);
    assert.equal(e.artifacts.length, 2);
    return true;
  });
});

test("a missing file is an artifact, not a rejection", async () => {
  const a = await att("missing.txt");
  assert.equal(a.errors[0]!.code, "unpack-error");
});

test("inputs: lists, Sets in insertion order, URLs, Files, Blobs", async () => {
  const a = await att(new Set(["notes.txt", "docs/b.txt"]));
  assert.deepEqual(a.map((x) => x.meta.source), ["notes.txt", "b.txt"]);
  const fromUrl = await att(new URL(`file://${join(root, "notes.txt")}`));
  assert.equal(fromUrl[0]!.text, "plain notes");
  const files = await att([new File(["hello"], "h.md"), new Blob(["no name"])]);
  assert.deepEqual(files.map((x) => x.meta.source), ["h.md", "file"]);
});

test("bare bytes and other values are refused as artifacts", async () => {
  const a = await att([new Uint8Array([1, 2]), 42] as never);
  assert.deepEqual(a.errors.map((e) => e.code), ["unpack-error", "unpack-error"]);
});

test("options: the string's and the call's, the call's win; unknown ones warn", async () => {
  const { value, warnings } = captureWarnings(() => att("notes.txt[pagez: 1]"));
  const a = await value;
  assert.deepEqual(a[0]!.meta.warnings, ["Unknown option 'pagez' for .txt"]);
  assert.equal(warnings[0]!.type, "OptionWarning");
});

test("a folder gives its overview first", async () => {
  const a = await att("docs");
  assert.equal(a[0]!.meta.kind, "directory");
  assert.deepEqual(a.slice(1).map((x) => x.meta.source), ["a.md", "b.txt"]);
});

test("a signal stops reading", async () => {
  const controller = new AbortController();
  controller.abort(new Error("stop"));
  await assert.rejects(att("notes.txt", { signal: controller.signal }), /stop/);
});

test("att.with keeps its settings to itself", async () => {
  resetConfig();
  const strict = att.with({ prefer: "service-only" });
  assert.equal((await strict("notes.txt")).errors[0]!.code, "service-error");
  assert.equal((await att("notes.txt")).errors.length, 0);
  assert.throws(() => att.with({ nope: 1 } as never), /unknown setting 'nope'/);
});

test("configure merges and returns the settings", () => {
  resetConfig();
  assert.deepEqual(configure({ timeout: 5 }), { timeout: 5 });
  assert.deepEqual(configure(), { timeout: 5 });
  assert.throws(() => configure({ prefer: "nowhere" as never }), /prefer must be one of/);
  resetConfig();
});

test("a processor of your own, named, with typed options and base", async () => {
  processor({
    extensions: [".txt"],
    name: "shout",
    options: { volume: { type: "int", default: 1 } },
    async process(data, { volume }, { base }) {
      const standard = await base();
      return makeArtifact({ text: `${standard.text.toUpperCase()}${"!".repeat(volume ?? 1)}` });
    },
  });
  const a = await att("notes.txt[processor: shout, volume: 3]");
  assert.equal(a[0]!.text, "PLAIN NOTES!!!");
  assert.equal(a[0]!.meta.extra?.["processor"], "shout");
  assert.equal((await att("notes.txt"))[0]!.text, "plain notes");
});

test("a source of your own", async () => {
  source({ prefixes: ["mem://"], unpack: (input) => [new File([`you asked for ${input}`], "m.txt")] });
  assert.equal((await att("mem://x"))[0]!.text, "you asked for mem://x");
});

test("att.options and checkDeps", () => {
  const pdf = att.options(".pdf");
  assert.ok("pdf" in { pdf: att.options().processors[".pdf"] });
  assert.ok(pdf.some((o) => o.name === "pages"));
  const deps = checkDeps();
  assert.equal(deps.formats[".md"], true);
  assert.equal(deps.formats[".pdf"], false);
});
