# attachments-dev (TypeScript)

The TypeScript implementation of [Attachments](https://attachments.dev):
turn any file, folder or web page into text and pictures a language model
can read. It answers to the same contract as the Python package
([`../contract`](../contract)), case for case.

**Status: 0.1.0, not on npm yet. `att()` is not here yet.** What exists is
everything that happens *after* a file is read: the `Artifacts` result and
all its methods, the option syntax, page selections, options, and the wire
form. So TypeScript can already load what Python, the CLI or the server
saved, and do everything with it that Python does, with the same output to
the character. Reading files, folders and web addresses (`att()`) comes
next. The plan: [design/01-many-languages.md](../design/01-many-languages.md);
the API: [design/02-typescript-api.md](../design/02-typescript-api.md).

```ts
import { Artifacts } from "attachments-dev";

// what att("report.pdf") gives in Python, the CLI's --json, or the server
const a = Artifacts.fromWire(JSON.parse(saved));

a.text                        // the prompt text, file names included
a.claude("Summarize.")        // Anthropic messages, each page's pictures by its text
a.openai("Summarize.")        // OpenAI Chat Completions messages
a.lm15("Summarize.")          // one @lm15/lm15 Message
a.parts()                     // provider-neutral parts
a.chunk({ maxChars: 4000 })   // chunks for retrieval, page by page
a.estimateTokens()            // { text, images, total }
a.throwIfErrors()             // stop here if any file failed
JSON.stringify(a)             // the wire form again
```

## Where TypeScript differs, stated

- `raise_for_errors()` is `throwIfErrors()`: JavaScript throws.
- Method options with two words are camelCase (`maxChars`); options of
  `att()` will keep their contract names (`max_dim`), as in the string.
- No `ERROR_*` constants: `ErrorCode` is a string-literal type.
- Warnings go through `process.emitWarning` (types `OptionWarning`,
  `RequestLimitWarning`, `AttachmentsWarning`) in Node, `console.warn`
  elsewhere.
- `a.claude()` types a picture's `media_type` as the four types Claude
  accepts, so it fits `@anthropic-ai/sdk` without a cast. A picture of
  another type keeps its real type at run time; building the messages
  warns that Claude will refuse it.
- `map` gives a plain array; `filter`, `slice` and `concat` give
  `Artifacts` (Python: slicing gives `Artifacts`).

## Developing

```bash
npm ci
npm run check      # types
npm test           # the contract's cases, the DSL vectors, the API
npm run generate   # after contract/dsl-schema.json changes
../check           # everything: the contract, Python, TypeScript
```

No runtime dependencies. The Anthropic, OpenAI and lm15 packages are
development dependencies only: a test compiles the messages against their
types.
