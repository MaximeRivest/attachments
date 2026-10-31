# The TypeScript API

*Status, 2026-10-31: agreed, with the npm name `attachments-dev`
(decision 1). Built so far: `Artifacts` and the second import (`ts/`).*

*Earlier: proposal, nothing built. Companion to
`01-many-languages.md`, which says what the contract fixes; this note says
what a TypeScript user types. Where the two disagree, this one is newer.*

## The whole thing on one screen

```ts
import { att } from "attachments-dev";

const a = await att("report.pdf[pages: 1-4]");

a.text                        // the prompt text, file names included
`Summarize:\n\n${a}`          // the same text, in a template
a.images                      // every picture: { name, mimetype, bytes, page? }
a.errors                      // [{ source, code, message }]
a.tokens                      // estimated tokens, text and pictures

a.claude("Summarize.")        // Anthropic messages, each page's pictures by its text
a.openai("Summarize.")        // OpenAI Chat Completions messages
a.lm15("Summarize.")          // one lm15 Message
a.parts()                     // provider-neutral parts
a.chunk({ maxChars: 4000 })   // chunks for retrieval, by page
a.throwIfErrors()             // stop here if any file failed

// in one line, as in Python
const messages = await att("report.pdf").claude("Summarize.");

// options: in the string, or in an object with the same names
await att("scan.pdf", { pages: "1-4", ocr: true, max_dim: 1568 });

// anything: paths, folders, globs, URLs, repos, files from a form
await att(["notes/", "https://example.com/post", "github://owner/repo"]);
await att(fileInput.files[0]);
```

Everything else is either in that screen's shape or is for people writing
their own processors.

## The rules this follows

1. **One await, then plain values.** `att()` is the only thing that waits.
   Everything on the result is synchronous and pure, as in Python.
2. **A result is an array, an artifact is a plain object.** `a[0].text`,
   `a.length`, `for (const x of a)`, `JSON.stringify(a)` all work, because
   that is what they are.
3. **Option names are the contract's names, everywhere they appear.** The
   same `max_dim` in the string, in the object, in the documentation, in
   warnings, in `att.options()` and in the server's JSON. Everything that
   is TypeScript's own API (settings, method options) is camelCase.
4. **Never throws for a bad file.** A missing or broken file is an artifact
   with `meta.error`, as in Python. The promise rejects only for misuse
   (`TypeError`) or cancellation (`AbortError`).
5. **Web standards over our own types.** `Uint8Array` for bytes, `File`
   and `Blob` for files in hand, `URL` for addresses, `AbortSignal` to
   cancel. Nothing to learn that the platform does not already teach.
6. **Small main import.** `att`, `Artifacts`, `configure`,
   `AttachmentsError`, `checkDeps` and types. What processor authors need
   lives in a second import.

## The decisions, with the alternatives an expert would raise

### `att()` returns a promise you can also call methods on

```ts
const a = await att("report.pdf");                    // the usual
const m = await att("report.pdf").claude("Summarize."); // one line
const a2 = await att("folder/").throwIfErrors();      // stop on failures, one line
```

`att()` returns a real `Promise<Artifacts>` carrying the result's methods
and getters, each returning a promise of its result. This is what `ky`
does (`await ky.get(url).json()`), and it is what makes Python's one-liner
`att("report.pdf").claude("Q")` the same one line in TypeScript.

- *Rejected: a plain promise.* Then the one-liner is
  `(await att("report.pdf")).claude("Q")`, and stopping on errors in one
  expression is impossible. Python's most-used line would be the clumsiest
  one in TypeScript.
- *Rejected: a lazy builder* (nothing happens until you await). Work starts
  at the call, like `fetch`. Nothing is hidden.
- *Cost, stated:* the list of methods exists twice in the types (on
  `Artifacts` and on the pending promise). A test fails if they differ.
  Forgetting `await` gives a `Promise` where a value was expected; the
  compiler catches it in typed code, a template literal does not
  (`${att(x)}` prints `[object Promise]`).

### `Artifacts` extends `Array`

Python's `Artifacts` is a `list` of plain dicts. The TypeScript one is an
`Array` of plain objects with the same methods. `a[0]`, `a.length`,
spreading and iterating need no explanation.

- `map`, `filter` and `slice` return plain arrays (`Symbol.species` is
  `Array`), as slicing a Python `Artifacts` returns a `list`. To get the
  methods back: `Artifacts.from(a.filter(ok))`. The alternative (filter
  returns `Artifacts`) breaks `a.map(x => x.text)`, which would build an
  `Artifacts` of strings.
- `JSON.stringify(a)` gives the wire form (`toJSON()` is `toWire()`), so
  pictures become `bytes_b64` instead of an object of numbered bytes.
- `console.log(a)` in Node prints the same one-line summary as Python's
  `repr` (`<Artifacts: 1 artifact | 14,210 chars | ~4,100 tokens | 3 images>`,
  then any errors and warnings), not a wall of bytes.
- `String(a)` and `${a}` give the text, as `print(a)` and `f"{a}"` do.

*Rejected: a wrapper class* (`a.items[0]`, `a.at(0)`). One more thing to
learn, and every array function would need a forwarding method.

### Artifacts are plain objects, typed exactly as the contract says

```ts
interface Artifact {
  text: string;
  images: ImageItem[];
  audio: unknown[];   // reserved
  video: unknown[];   // reserved
  meta: Meta;
}
interface ImageItem { name: string; mimetype: string; bytes: Uint8Array; page?: number }
interface Meta {
  source: string;
  kind?: "text" | "pdf" | "table" | "document" | "html" | "slides" | "image" | "directory" | (string & {});
  via?: "service";
  error?: { code: ErrorCode; message: string };
  note?: string;
  warnings?: string[];
  segments?: Segment[];
  extra?: Record<string, unknown>;
}
type ErrorCode =
  | "missing-dependency" | "password-required" | "parse-error" | "unpack-error"
  | "service-error" | "invalid-option" | "processing-error";
```

The contract's keys are all one word (`mimetype`, `segments`, `extra`), so
the objects look native. "Absent, never null" is the contract's rule and
is exactly TypeScript's optional property; the types are written for
`exactOptionalPropertyTypes`.

*A difference, stated:* Python exports `ERROR_PARSE = "parse-error"` and
six more. TypeScript exports the `ErrorCode` type only: a string literal is
checked by the compiler and completed by the editor, which is the reason
the constants exist in Python. Having both would be two spellings.

### Option names: the contract's, not camelCase

```ts
await att("photo.heic", { max_dim: 1024, image_format: "jpeg" });
```

`01-many-languages.md` proposed `maxDim`. This note reverses it. Options are
not TypeScript's own words: they are a shared vocabulary that appears in
the string (`[max_dim: 1024]`), in the option list and cheat sheet, in
warnings ("unknown option `max_dimm`, did you mean `max_dim`?"), in
`att.options()`, in the server's request body, and in Python. With
camelCase, one TypeScript program would spell the same option two ways
depending on where it wrote it, and every warning would need translating.

The TypeScript LLM SDKs made the same choice for the same reason: OpenAI's
and Anthropic's put request fields in their API spelling
(`{ max_tokens: 1024 }`) and the client's own settings in camelCase
(`maxRetries`). Attachments users are already used to that split. Only
8 of the 37 options have two words (`max_dim`, `max_pages`, `max_files`,
`max_screens`, `max_size`, `image_format`, `ocr_engine`, `embedded_images`).

The object's type is generated from `contract/dsl-schema.json`: every
option, its value type, and its help text as documentation, so hovering
`max_dim` in the editor shows "Downscale so the longest side is at most
this many pixels".

- *Aliases* (`pw`, `slides`, `sep`, `css`, `branch`, …) work in the string,
  as the contract says, but are not in the object's type: each concept
  completes once. Python's keyword arguments accept them; TypeScript's
  object does not. Stated.
- *Rejected: options typed by file extension* (`att("x.pdf", …)` offering
  PDF options only). Folders, archives and repositories take every
  format's options, and a source's options mix with a processor's. A
  wrong compile error would be worse than Python's warning. Unknown
  options warn at run time, exactly as in Python.

Besides the contract's options, the object takes two words of
TypeScript's own, both one word so the casing question never comes up:
`prefer` (as in Python) and `signal` (an `AbortSignal`, as `fetch` takes).

### Settings: `configure()` for a script, `att.with()` for a server

```ts
configure({ apiKey: "att_…", prefer: "local" });    // process-wide, as in Python

const hosted = att.with({ apiKey: tenant.key, prefer: "service-only" });
await hosted("scan.pdf");                            // only this one
```

In Node, `ATTACHMENTS_API_KEY` and `ATTACHMENTS_SERVICE_URL` are read as in
Python. As in Python, nothing is ever sent to a server unless a key or a
server address was set.

Python takes `api_key=` on each call. A Node server answers many users at
once, so process-wide settings are a hazard there: two requests would
share one tenant's key. `att.with()` returns a new `att` with its own
settings (the name follows `Array.prototype.with` and Temporal's `with`:
a copy with changes). It also has `.fromPrompt`, `.options` and the rest.

*A difference, stated:* there is no `apiKey` on a single call; use
`att.with({ apiKey })(input)`. Settings (`apiKey`, `serviceUrl`,
`timeout`, `prefer`) are TypeScript's own words, so they are camelCase.

### Inputs: strings, URLs, files

```ts
type Input = string | URL | Blob | readonly (string | URL | Blob)[];
```

- A string is what Python takes: a path, folder, glob, `https://`,
  `github://`, `.zip`, each with `[options]`.
- A `URL`, including `new URL("./data.csv", import.meta.url)`, the
  standard way to name a file next to a module.
- A `File` (or `Blob`) is bytes in hand: an upload, a form, a database
  row, `new File([buffer], "report.pdf")` for a Node `Buffer`. Its name
  picks the processor. A `Blob` without a name is recognized by its type
  and its first bytes. There is no `[options]` in a file's name; pass the
  object.
- *Rejected: a bare `Uint8Array` with a `filename` option.* `File` already
  is named bytes, in every browser and in Node 20 and later. One way.

In a browser, only URLs (where the server allows it) and files work;
paths, folders and `fromPrompt` with a `root` refuse with a message that
says so. Several inputs are read at the same time, a few at a time; the
result is in input order, as the contract requires.

### Errors: `throwIfErrors()`

```ts
try {
  const a = await att("folder/").throwIfErrors();
} catch (e) {
  if (e instanceof AttachmentsError) e.errors, e.artifacts; // what failed, and everything read
}
```

Python's `raise_for_errors()`, renamed: JavaScript throws, it does not
raise, and the platform's own pattern is `signal.throwIfAborted()`. Same
behavior: every input is read first, one error lists every failure, and
the files that worked are not lost. This is the one word that changes
across languages, besides casing, because the word is the language's
mechanism (lm15's rule for errors: "the class name and the code are the
family; the mechanism is the language's").

### Adapters return what each SDK takes

```ts
await anthropic.messages.create({ model, max_tokens: 1024, messages: a.claude("Summarize.") });
await openai.chat.completions.create({ model, messages: a.openai("Summarize.") });
await router.complete({ model, messages: [a.lm15("Summarize.")] });
```

The return types are written to fit `@anthropic-ai/sdk`'s `MessageParam[]`,
`openai`'s `ChatCompletionMessageParam[]` and `@lm15/lm15`'s `Message`, and
a test compiles them against the real packages. None of the three is a
dependency at run time: each is plain data. Method options are camelCase
where they are two words (`chunk({ maxChars, maxTokens, overlap,
sources })`) and the same as Python where they are one (`sources`,
`interleave`, `prompt`, `tier`). The parts themselves are contract data,
so their keys stay as written (`{ type: "image", media_type, data }`).

### Warnings go where Node puts warnings

An unknown option, or a request bigger than a provider accepts, gives a
warning, as Python's `OptionWarning` and `RequestLimitWarning` do. In Node
it goes through `process.emitWarning` with that type name (silenced with
`--no-warnings`, observable with `process.on("warning")`); in a browser,
`console.warn`. The same text is on `meta.warnings`, where the contract
puts it.

### Extending: one object, typed from its own options

```ts
import { processor, makeArtifact } from "attachments/extend";

processor({
  extensions: [".pdf"],
  name: "invoice",                                   // att("x.pdf[processor: invoice]")
  detect: (data, filename) => filename.startsWith("INV-"),
  options: { currency: { type: "str", default: "EUR", help: "Currency of the totals" } },
  async process(data, { filename, currency }) {      // currency: string, from the declaration
    return makeArtifact({ text: await readInvoice(data, currency) });
  },
});

source({ prefixes: ["s3://"], async unpack(url, { signal }) { return [new File([body], key)] } });
```

Python's decorator, as one object: TypeScript decorators work on classes
only. Processors may be `async`. A source returns `File`s, the same named
bytes `att()` takes. Everything for authors (`makeArtifact`,
`errorArtifact`, `missingDepArtifact`, `missingPart`, `normalizeArtifact`,
`isMissingDependency`, `lacksDependency`, `parseDsl`, `formatDsl`,
`hasLocal`, `hasService`) has Python's names, camelCased, in this second
import.

*Left out, stated:* Python's function forms of the methods (`render_text`,
`to_parts`, `to_claude_messages`, `estimate_tokens`, …) and the registry
plumbing (`processors`, `reset_processors`, `get_processors_copy`,
`extra_unpack_handlers`). A method on the result is the one way; an array
from somewhere else becomes one with `Artifacts.from(array)` or
`Artifacts.fromWire(json)`.

## The surface, complete

Main import:

| Python | TypeScript |
|---|---|
| `att(x, **options)` | `att(x, options?)` → pending `Artifacts` |
| `att.from_prompt(text, root=, urls=)`, `from_prompt` | `att.fromPrompt(text, { root, urls, ...options })` |
| `att.options(ext)`, `options()` | `att.options(ext?)` |
| `att.help()` | `att.help()` |
| (per-call `api_key=`) | `att.with(settings)` |
| `configure(...)`, `get_config()`, `reset_config()` | `configure(settings)`, `configure()` returns the current settings |
| `check_deps()` | `checkDeps()` (async: it tries optional imports) |
| `Artifacts`, `Artifacts.from_wire` | `Artifacts`, `Artifacts.fromWire`, `Artifacts.from` |
| `.text`, `.images`, `.errors`, `.tokens` | same |
| `.to_text(sources=)` | `.toText({ sources })` |
| `.parts(sources=, interleave=, prompt=)` | `.parts({ sources, interleave, prompt })` |
| `.claude(prompt, sources=, interleave=)`, `.openai(…)`, `.lm15(…)` | `.claude(prompt?, { sources, interleave })`, same for the others |
| `.chunk(max_chars=, max_tokens=, overlap=, sources=)` | `.chunk({ maxChars, maxTokens, overlap, sources })` |
| `.estimate_tokens(tier=)` | `.estimateTokens({ tier })` → `{ text, images, total }` |
| `.raise_for_errors()` | `.throwIfErrors()` |
| `.to_wire()` | `.toWire()`, and `JSON.stringify(a)` |
| `repr(a)`, `str(a)` | `console.log(a)` in Node, `String(a)` |
| `AttachmentsError` | `AttachmentsError` (`errors`, `artifacts`) |
| types `Artifact`, `ImageItem`, `Meta`, `Segment`, `ErrorInfo` | same, plus `ErrorCode`, `Options`, `Settings`, `Input` |

Second import (`…/extend`): `processor`, `source`, `Option` (a type), and
the helpers listed above.

Not in TypeScript: the command line, the MCP server, the HTTP server, the
skill, local OCR, audio and Office pictures (the service does them), and
the local OCR settings (`ocr_workers` and the other `ocr_*` settings of
`configure`). No progress bar: a library does not draw on the terminal.

## What this asks of the contract

None of the above changes what Python does, except:

- **Named bytes as input** (`File` here) needs a rule in the contract: what
  `meta.source` is for bytes with a name and without one, and how a
  nameless file is recognized. Python gets the same input (decision 3 of
  `01-many-languages.md`).
- **Several inputs read at once** must give the same result as one by one.
  The contract already fixes the order; a case should check it.

## Decisions for Maxime

1. **The npm name. Correcting the earlier note:** the `@attachments` scope
   belongs to someone else (it holds their `@attachments/serendipity`
   packages), so `@attachments/…` is not possible. `attachments` itself is
   someone's package, last published in 2022 (0.7.1). Free today:
   the scope `@attachments-dev` (the domain's name), `attachments-dev`,
   `attachments-js`. Recommendation: ask that package's owner to hand over
   `attachments`, since `import { att } from "attachments"` is the same
   line as Python's. Claim the `@attachments-dev` scope now either way (it
   is free and costs nothing) and publish there if the owner says no.
2. **The pending promise with methods.** It is the boldest choice here and
   the one that makes the one-liner work. The alternative is plain
   `await att(x)` and nothing else.
3. **Option names as the contract spells them** (`max_dim`), against
   TypeScript's usual camelCase. Recommended above; it is a choice that
   cannot be undone after the first release.
4. **`throwIfErrors`** instead of `raiseForErrors`.
5. **A Vercel AI SDK adapter.** The AI SDK is the most used way to call
   models from TypeScript; Python has nothing like it. FunctAI's plan keeps
   integrations that belong to one ecosystem in that language. A `.parts()`
   result is one line away from AI SDK parts, so this can wait for
   someone to ask.
