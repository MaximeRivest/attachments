# attachments-dev (TypeScript)

The TypeScript implementation of [Attachments](https://attachments.dev):
turn any file, folder or web page into text and pictures a language model
can read. It answers to the same contract as the Python package
([`../contract`](../contract)), case for case, and is checked against
Python's own server.

**Status: 0.1.0, not on npm yet.** No dependencies. Node 22.18+, Deno or
Bun for files and folders; browsers for web addresses and `File`s.

```ts
import { att } from "attachments-dev";

const a = await att("report.pdf[pages: 1-4]");

a.text                        // the prompt text, file names included
a.claude("Summarize.")        // Anthropic messages, each page's pictures by its text
a.openai("Summarize.")        // OpenAI Chat Completions messages
a.lm15("Summarize.")          // one @lm15/lm15 Message
a.parts()                     // provider-neutral parts
a.chunk({ maxChars: 4000 })   // chunks for retrieval, page by page
a.throwIfErrors()             // stop here if any file failed

// one line: any method on the pending result
const messages = await att("report.pdf").claude("Summarize.");

// options in the string, or in an object with the same names
await att("scan.pdf", { pages: "1-4", max_dim: 1568 });

// folders, patterns, archives, web addresses, repositories, files in hand
await att(["notes/", "src/**/*.ts", "https://example.com/post", "github://owner/repo"]);
await att(fileInput.files[0]);
```

## What reads what

TypeScript reads these itself, exactly as Python does: text (Markdown,
code, JSON, YAML, …, and any file that looks like text), **CSV and TSV**
(the separator guesser Attachments carries, and Python's reader, ported), **Jupyter notebooks**,
and the text of **SVG** drawings (with an XML parser that accepts and
refuses what Python's does). It unpacks folders, patterns, zip and tar
archives, downloads and GitHub repositories the same way too.

Every other format (PDF, Word, PowerPoint, Excel, HTML, images, audio),
and an SVG's picture, is read by the **Attachments service**, the Python
package running as a server, when you configure one:

```ts
import { configure } from "attachments-dev";
configure({ serviceUrl: "https://api.attachments.dev/v1" }); // or your own: python -m attachments.server
configure({ apiKey: "att_…" });                              // a key implies the hosted service
```

Nothing is ever sent anywhere unless a key or an address is set. Without
a service, such a file is an artifact with error `missing-dependency`,
exactly what Python gives when its extra is not installed. A server
answering many users keeps keys apart with `att.with({ apiKey })`.

## Where TypeScript differs, stated

- **`att()` returns a promise** (reading files and fetching are
  asynchronous here); everything on the result is synchronous.
- `raise_for_errors()` is `throwIfErrors()`: JavaScript throws.
- Options of `att()` keep their contract names (`max_dim`, in the string
  and in the object). Method options with two words are camelCase
  (`chunk({ maxChars })`), and so are settings (`apiKey`, `serviceUrl`).
- Aliases (`pw`, `slides`, `css`, …) work in the string only; the object
  takes each option once. An unknown key in the object is a compile
  error; options of processors of your own are added to the type by
  declaration merging:
  ```ts
  declare module "attachments-dev" { interface Options { currency?: string } }
  ```
- Bytes in hand are a `File` or `Blob` (Python: an open binary file). A
  `Set` keeps its insertion order (Python sorts a set).
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
- **Processors of your own** take `(data, options, context)`: the resolved
  options (typed from their declarations) apart from the file name,
  `base` and `signal`, so an option can never collide with them. No
  decorators: `processor({ extensions, name, detect, options, process })`.
- **Picture labels** (`watermark`) are drawn by the service: TypeScript
  cannot draw, so it sends the option along.
- `[summary: true]` on a CSV: Python adds a summary with pandas;
  TypeScript returns the table with a warning (the service has it).
- Integers in a notebook past 2^53 lose precision when printed.
- **Not here**: `.tar.bz2` and `.tar.xz` (the contract's `archive/bz2-xz`
  extension: refused with `unpack-error`), sparse tar members, zip members
  compressed with bzip2 or lzma; the command line, the MCP server, the HTTP
  server and the agent skill (Python's); local OCR and the other heavy
  readers (the service has them).
- In a browser there is no file system: inputs are addresses (where the
  server allows it) and `File`s. Folders, patterns, repositories and
  `fromPrompt` file mentions need Node, Deno or Bun.
- **Private addresses**: `att.with({ blockPrivateUrls: true })` (or
  `ATT_BLOCK_PRIVATE_URLS=1`) refuses addresses that resolve to private
  networks, checked when each connection is made (redirects too), with
  Python's list of public addresses (Python 3.12's `ipaddress`).

## Developing

```bash
npm ci
npm run check      # types
npm test           # the contract's cases, the API, and against Python's server
npm run generate   # after contract/dsl-schema.json or reading-data.json change
../check           # everything: the contract, Python, TypeScript
```

The tests against Python (its server, and a differential test feeding
both languages the same random CSV, notebook and SVG bytes; set
`ATT_FUZZ_SEED` and `ATT_FUZZ_SVGS` to explore further) run when
`../.venv` exists (`uv sync` in the repository); the Anthropic, OpenAI and lm15 packages are
development dependencies only (a test compiles the messages against their
types).
