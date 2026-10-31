# The Attachments contract

What every implementation of Attachments must do the same way, whatever
its language. Python (`src/attachments`) and TypeScript (`ts/`) answer
to it; when one of them and this folder disagree, the implementation is
wrong. To change a rule: change it here first, then every implementation,
in the same commit.

This is the authority, not the Python package. Python came first and most
cases were drafted from what it did (see *Cases*), but a case that a
person has reviewed outranks Python's behavior, and a Python bug found
here is fixed in Python.

## What is here

| File | What it fixes |
|---|---|
| [IR-CONTRACT.md](IR-CONTRACT.md) | the Artifact: its shape, error codes, processor and routing rules, the wire form |
| [artifact.schema.json](artifact.schema.json) | the Artifact's wire form as JSON Schema |
| [dsl-grammar.md](dsl-grammar.md), [dsl-test-vectors.json](dsl-test-vectors.json) | the `source[key: value]` syntax |
| [dsl-schema.json](dsl-schema.json) | every option: name, type, aliases, default, help (written by Python's `scripts/gen_dsl_assets.py`; a change to it is a contract change) |
| [presenting.md](presenting.md) | turning artifacts into what a model reads: text, parts, Claude/OpenAI/lm15 messages, chunks, token estimates, request limits, the printed summary; option resolution and page selections |
| [cases/](cases/) | the cases every implementation must answer the same way |

Still to write (`design/01-many-languages.md`, step 1): sources (folders,
ignore rules, the folder overview), routing with a fake service, and the
server's HTTP API.

## Text, numbers and white space

These hold everywhere in the contract, because languages disagree on them
by default:

- **A string's length and every offset count Unicode code points.**
  `Segment.start`/`end`, `len(text)` in token estimates, chunk sizes, the
  160-character cut of error messages: code points, not UTF-16 units
  (JavaScript's `.length`) or bytes. `"😀"` is one.
- **White space is Python's `str.isspace()` set**: tab, line feed, vertical
  tab, form feed, carriage return, U+001C to U+001F, space, U+0085,
  U+00A0, U+1680, U+2000 to U+200A, U+2028, U+2029, U+202F, U+205F,
  U+3000. *Strip* removes these at both ends. Not white space: U+FEFF
  (JavaScript's `trim()` removes it; the contract keeps it).
- **Rounding to an integer is half to even** (`round(2.5) == 2`), and a
  number shown with one decimal (`32.2 MB`, `~3.2k tokens`) is the
  binary value rounded half to even: 32.25 shows as `32.2`. JavaScript's
  `Math.round` and `toFixed` round half up and must not be used as is.
- **Thousands are separated by commas** (`12,345 chars`), whatever the
  locale.
- **JSON size** (the request-limit estimate) is the length of Python's
  `json.dumps` of the string: every character outside ASCII written as
  `\uXXXX` (6 characters; 12 outside the BMP), `\"`, `\\`, `\n`, `\r`,
  `\t`, `\b`, `\f` as 2, other control characters as 6.

## Cases

`cases/*.json`, one file per area, each a list of cases: the input, the
call, and the expected answer. They are written by
[cases/make.py](cases/make.py) and nothing else; `./check` fails when the
files differ from what it writes.

The inputs are chosen from the rules: each situation a rule speaks of,
its edges, and the text that trips implementations (characters outside
the BMP, white space languages disagree on, rounding ties). The expected
answers were drafted by running Python (`tests/_contract.py`) and each
file says `"review": "draft"` until a person has read its cases against
the rules. A draft pins today's behavior: an implementation that differs
raises a question about the rule before it is "wrong".

Conventions in the cases:

- Artifacts are in wire form (`bytes_b64`).
- A long string is written `{"repeat": "A", "times": 33000000}`.
- Arguments use the contract's names (`max_chars`, `sources`); each
  implementation maps them to its own spelling.
- `{"throws": true}` means the call must fail with the language's error
  for bad arguments; the message is not pinned.
- `"warnings"` lists warnings the call must give, by kind
  (`request-limit`, `named-labels`).

| Area | Cases about |
|---|---|
| `present` | text, parts, Claude, OpenAI and lm15 messages, for every scene × names shown or not × interleaving × prompt |
| `chunk` | packing segments, windows, overlap, caps |
| `tokens` | Claude's picture tokens for many sizes, both tiers; the estimate of artifacts |
| `imagesize` | a picture's size from its first bytes |
| `limits` | the problems a request has against Claude's and OpenAI's limits, word for word |
| `wire` | round trips; what `from_wire` refuses (base64 rules included) |
| `dsl` | formatting options back into the syntax, and parsing them again |
| `pages` | page selections: what parses, its canonical text, which pages of a document it picks |
| `options` | resolving options against a format's schema: aliases, coercion, unknown and invalid options, suggestions |
| `summary` | the printed one-line summary and its lines; the message of the error that lists failures |

Each implementation runs every case: Python in
`tests/test_contract_cases.py`, TypeScript in `ts/tests/contract.test.ts`.
