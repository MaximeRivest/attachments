/** The DSL's normative vectors (contract/dsl-test-vectors.json) and the generated files. */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

import { parseDsl } from "attachments-dev/extend";
import { optionsModule, readingModule, readReadingData, readSchema, schemaModule } from "../tools/generate.ts";

const here = dirname(fileURLToPath(import.meta.url));
const vectors = JSON.parse(readFileSync(join(here, "..", "..", "contract", "dsl-test-vectors.json"), "utf8")).vectors;

for (const v of vectors) {
  test(`dsl vector: ${v.name}`, () => {
    const [source, options] = parseDsl(v.input);
    assert.equal(source, v.source);
    assert.deepEqual(options, v.options);
  });
}

test("integers past 2^53 stay as written", () => {
  assert.deepEqual(parseDsl("x[id: 12345678901234567890]")[1], { id: "12345678901234567890" });
});

test("src/generated is what tools/generate.ts writes from the contract", () => {
  const schema = readSchema();
  const generated = join(here, "..", "src", "generated");
  assert.equal(readFileSync(join(generated, "schema.ts"), "utf8"), schemaModule(schema), "run: npm run generate");
  assert.equal(readFileSync(join(generated, "options.ts"), "utf8"), optionsModule(schema), "run: npm run generate");
  assert.equal(readFileSync(join(generated, "reading.ts"), "utf8"), readingModule(readReadingData()), "run: npm run generate");
});
