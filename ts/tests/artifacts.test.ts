/** `Artifacts` as TypeScript code uses it: an array with methods. */

import assert from "node:assert/strict";
import { test } from "node:test";
import { inspect } from "node:util";

import type Anthropic from "@anthropic-ai/sdk";
import { Message as Lm15Message, type Request as Lm15Request } from "@lm15/lm15";
import type OpenAI from "openai";

import { type Artifact, AttachmentsError, Artifacts } from "attachments-dev";

const art = (text: string, source: string, extra: Partial<Artifact["meta"]> = {}): Artifact => ({
  text,
  images: [],
  audio: [],
  video: [],
  meta: { source, ...extra },
});
const png = new Uint8Array([0x89, 0x50, 0x4e, 0x47]);
const sample = (): Artifacts =>
  Artifacts.from([
    art("Alpha.", "a.txt"),
    { ...art("Page one.", "r.pdf"), images: [{ name: "p1.png", mimetype: "image/png", bytes: png, page: 1 }] },
    art("", "broken.pdf", { error: { code: "parse-error", message: "not a PDF" } }),
  ]);

test("it is an array of plain objects", () => {
  const a = sample();
  assert.ok(Array.isArray(a));
  assert.equal(a.length, 3);
  assert.equal(a[0]!.text, "Alpha.");
  assert.deepEqual([...a].map((x) => x.meta.source), ["a.txt", "r.pdf", "broken.pdf"]);
});

test("filter, slice and concat keep the methods; map gives a plain array", () => {
  const a = sample();
  assert.ok(a.filter((x) => !x.meta.error) instanceof Artifacts);
  assert.equal(a.filter((x) => !x.meta.error).errors.length, 0);
  assert.ok(a.slice(0, 1) instanceof Artifacts);
  assert.ok(a.concat(a) instanceof Artifacts);
  const sources = a.map((x) => x.meta.source);
  assert.ok(!(sources instanceof Artifacts));
  assert.deepEqual(sources, ["a.txt", "r.pdf", "broken.pdf"]);
});

test("String, template literals and .text are the prompt text", () => {
  const a = sample();
  assert.equal(String(a), a.text);
  assert.equal(`${a}`, "## a.txt\nAlpha.\n\n## r.pdf\nPage one.");
});

test("console.log shows the summary, never bytes", () => {
  assert.equal(
    inspect(sample()),
    "<Artifacts: 3 artifacts | 15 chars | ~4.8k tokens (images ~4.8k) | 1 image | 1 error>\n  ! broken.pdf: parse-error — not a PDF",
  );
});

test("JSON.stringify writes the wire form, and fromWire reads it back", () => {
  const a = sample();
  const json = JSON.parse(JSON.stringify(a));
  assert.equal(json[1].images[0].bytes_b64, "iVBORw==");
  assert.equal(json[1].images[0].bytes, undefined);
  const back = Artifacts.fromWire(json);
  assert.deepEqual(back[1]!.images[0]!.bytes, png);
  assert.deepEqual(back.toWire(), a.toWire());
});

test("throwIfErrors lists every failure and keeps what worked", () => {
  const a = sample();
  assert.throws(() => a.throwIfErrors(), (e: unknown) => {
    assert.ok(e instanceof AttachmentsError);
    assert.equal(e.message, "broken.pdf: parse-error — not a PDF");
    assert.equal(e.artifacts.length, 3);
    return true;
  });
  const ok = a.filter((x) => !x.meta.error);
  assert.equal(ok.throwIfErrors(), ok);
});

test("the messages fit the SDKs' own types", () => {
  const a = sample();
  const claude: Anthropic.MessageParam[] = a.claude("Summarize.");
  const openai: OpenAI.ChatCompletionMessageParam[] = a.openai("Summarize.");
  const request: Lm15Request = { model: "claude-sonnet-4-5", messages: [a.lm15("Summarize.")] };
  assert.equal(claude[0]!.role, "user");
  assert.equal(openai[0]!.role, "user");
  assert.equal(request.messages.length, 1);
});

test("lm15 accepts the message as its own", () => {
  const m = sample().lm15("Summarize.");
  const checked = Lm15Message.create(m);
  assert.deepEqual(
    checked.parts.map((p) => p.type),
    ["text", "image", "text"],
  );
});
