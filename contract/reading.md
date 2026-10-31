# Reading inputs (v1)

What `att()` does between an input and its artifacts: which inputs it
takes, how an input becomes files (sources), which processor reads each
file, when the service is asked, and what comes back. The routing rules in
[IR-CONTRACT.md](IR-CONTRACT.md) stand; this page completes them. Text and
number rules are in [README.md](README.md#text-numbers-and-white-space);
the cases in `cases/` (areas `inputs`, `ignore`, `globs`, `trees`,
`archives`, `downloads`, `naming`, `routing`, `text`, `mentions`) are the
examples.

`att()` never fails for a bad input or a bad file: each comes back as an
artifact with `meta.error`. It fails only for misuse that no input could
cause (an argument of the wrong kind to a setting).

## Inputs

An input is one of:

- **Text**: a path, folder, wildcard pattern, `file://` URI, `~/…`,
  `http(s)://` address, `github://owner/repo`, or a prefix a source was
  registered for, each optionally followed by `[options]`
  ([dsl-grammar.md](dsl-grammar.md)).
- **A path object** (Python `os.PathLike`, TypeScript `URL`): its text,
  without options parsing in TypeScript's `URL` (a URL has no `[options]`).
- **Named bytes** (Python: a binary file object, its `name`'s last path
  segment; TypeScript: `File`/`Blob`, its `name`): read as a local file of
  that name would be (archives expanded by name), never parsed for
  options. Without a name, it is called `file`.
- **A list** of inputs, read in order, nested lists flattened. Python sorts
  a `set` (it has no order); TypeScript keeps a `Set`'s insertion order.

Anything else is one artifact with error `unpack-error` whose source names
what was given. Bare bytes (`bytes`, `Uint8Array`) are refused this way,
with a message pointing to the named form: without a name, the bytes'
format would be a guess.

## Options

Options come from the input's `[...]` and from the call (the call's win on
the same key). They are resolved per file against the processor's
declarations ([presenting.md](presenting.md#options-and-page-selections)),
and an option written in the string keeps its text: an option of type `str`
takes the text as written (trimmed, unquoted), so `[password: 007]` is
`"007"` and `[ref: 1.10]` is `"1.10"`; every other type takes the typed
value.

Before files are read, two kinds of options are taken out:

- **Folder options** (`files`, `tree`, `ignore`, `hidden`, `glob`/`include`,
  `recursive`, `max_files`, `max_size`) when the input is a local path, a
  pattern, a repository or an archive address; they shape the tree and are
  not given to processors. Given for a single file, they are dropped with
  one warning on each artifact: `Folder options (NAMES) apply to folders,
  patterns, repositories and archives; ignored for a single file.`
- **Source options** declared by the input's source (`ref` for GitHub).

## Sources

The first that applies, in this order:

1. **Registered prefixes** (`source(...)`): the source's function gives the
   files.
2. **GitHub repository roots**: `github://owner/repo` or
   `https://github.com/owner/repo[.git]` (exactly two path segments).
   `owner/repo` must match `^[a-zA-Z0-9][-a-zA-Z0-9_.]*[a-zA-Z0-9]?/[a-zA-Z0-9][-a-zA-Z0-9_.]*[a-zA-Z0-9]?(\.git)?$`
   and contain none of `--`, `..`, `;`, `|`, `&`, `$`, `` ` ``, line breaks.
   A shallow `git clone --depth 1 [--branch REF]` into a temporary folder,
   read as a folder (kind `repo`, root name `owner/repo`, plus `@REF`),
   then deleted.
3. **Web addresses** (`http://`, `https://`): one download (below); an
   archive by name is expanded.
4. **A local folder** (`file://` and `~` are local paths): a tree (below).
5. **A local file**: its bytes, named by its last path segment; an archive
   by name is expanded. A file named on its own is read whatever the skip
   rules would say.
6. **A wildcard pattern** (`*`, `?` or a valid `[...]` in any segment),
   checked after 4 and 5 so a file named `a[1].txt` is that file.
7. Otherwise: error `unpack-error`.

A source that fails gives one `unpack-error` artifact for the input; when
the service is configured and the mode is not `local-only`, the service's
`/unpack` is asked first (web addresses only), and both failures are
named.

### Trees: folders, patterns, repositories, archives

Read in two steps. **List**: walk depth first, each folder's entries
sorted by name in code point order; a folder's files come before its
subfolders. Each entry is checked by the skip rules (below); a folder that
is skipped is not entered. Links that lead outside the tree's root are
skipped (`link outside the folder`); a link to a folder inside the tree
is not followed (the folder is read where it is); only regular files are
read (`not a regular file`); entries that cannot be read are skipped
(`unreadable`). With `recursive: false`, subfolders are skipped
(`subfolder (recursive: false)`). With `glob`, files whose path does not
match are skipped (`not matching glob`). The walk stops after 200,000
entries (`ATT_MAX_SCAN_ENTRIES`).

**Read**: take the listed files in order. A file is read if one more file
fits `max_files` (default 1,000; 0 = no limit) and its size fits what is
left of `max_size` (default 256 MiB, `50MB`-style text: KB/MB/GB/TB are
powers of 1000, KiB/MiB/GiB/TiB of 1024, a number alone is bytes; 0 = no
limit). A file that does not fit is not read and counted; the first limit
that stopped a file is the tree's `limit`. A file whose first bytes are a
private key (below) is skipped as a secret and gives back its room. An
archive inside a tree takes no room itself: its members do, one by one,
through the same rules. With `files: false`, nothing is read: the listing,
within the limits, makes the overview.

Names: a tree's files are named by their path from the tree's root
(`src/app.py`); archive members by the archive's name, `/`, their path.

### Skip rules

Checked in this order; the first that decides wins:

1. **Version control** folders (`.git`, `.hg`, `.svn`, `.bzr`, `_darcs`,
   `.jj`, `.pijul`): always (`vcs`; never shown in the overview).
2. **The `ignore` option**: patterns in `.gitignore` syntax, separated by
   commas or line breaks; `!pattern` keeps what a later rule would skip
   (`ignore option`). The words `none`, `raw`, `all` turn off rules 3–6;
   `standard`, `auto`, `default`, `gitignore`, `attachmentsignore` are
   no-ops; `minimal` is a no-op with a warning.
3. **Secrets** (`secret`): the list `SECRET_PATTERNS`, and, after reading,
   any file whose first 256 bytes start (after an optional UTF-8 BOM and
   white space) with `-----BEGIN … PRIVATE KEY-----` (optionally ` BLOCK`)
   or `PuTTY-User-Key-File-N`. `!name` in `ignore` keeps it.
4. **Generated** (`generated`): the list `GENERATED_PATTERNS`, and folders
   holding `pyvenv.cfg` or a `CACHEDIR.TAG` starting with
   `Signature: 8a477f597d28d172789f06886806bc55`.
5. **Hidden** (`hidden`): a name starting with `.`, unless `hidden: true`.
6. **Ignore files** (`ignore file`): `.gitignore` then `.attachmentsignore`
   (the later wins) in each folder, deeper folders first; then, when the
   tree is inside a git repository, the ignore files of its parent folders
   up to the repository root, closest first, and `.git/info/exclude`.
   Honoured outside a repository too.

The pattern lists are `SECRET_PATTERNS` and `GENERATED_PATTERNS` in
`src/attachments/_sources/_ignore.py`, copied into each implementation
with a test that the copy is equal.

**Gitignore patterns.** A line is trimmed of trailing white space unless
escaped (`\ `); blank lines and `#` lines are skipped; `!` negates; `\!`
and `\#` start a literal; a trailing `/` matches folders only. A pattern
with a `/` other than at its end is anchored to the ignore file's folder;
otherwise it matches at any depth. `*` and `?` never cross `/`; `**/` is
any number of folders; a trailing `/**` everything inside; `[...]`
classes (`!` or `^` negates, never matching `/`); `\x` is `x`. Within one
list, the last matching line decides. A pattern that does not compile is
ignored.

**Wildcard patterns** (inputs): split into the static folder before the
first segment with a wildcard, and the rest. `*`, `?`, `[...]` stay within
one segment; `**` is any number of folders. A wildcard does not match a
leading dot unless the segment starts with one or `hidden: true`, and
hidden folders are entered only then. Files are named relative to the
static folder. A pattern with no files is an `unpack-error` naming what
the skip rules left out.

### The overview

One artifact before a tree's files, with `meta.kind` `directory`, when the
tree is a folder or repository (`tree: auto`), when `tree: true`, when
`files: false`, when a limit stopped reading, the walk was cut short,
there are warnings, or nothing was read and something was skipped. Its
text, line by line:

```
<Folder|Repository|Files matching|Archive> <input as given> — N file(s) read, SIZE
Git: <branch or detached> @ <commit[:8]> (<origin, without credentials>)
Stopped at <limit>: <value> — N more file(s) not read. Raise it with [<limit>: ...] (0 = no limit).
Skipped:
- <reason>: N folder(s) and N file(s) (<up to 5 examples>, …) — <remedy>

<the tree, or (no files)>
```

With `files: false` the header says `— N file(s), SIZE (contents not read:
files: false)`. `SIZE` is bytes in powers of 1000 with one decimal
(`999 B`, `48.2 KB`, `3.4 MB`, `1.0 GB`). The git line appears when the
tree is in a repository; it reads `.git` files only, never runs git. The
tree lines appear when the overview shows the tree (`tree: auto` for
folders and repositories, `true`, or `files: false`): the root name and
`/`, then `├── `, `└── `, `│   `, `    ` as `tree` draws them, an archive
annotated `  (N files)`. Reasons, their names and remedies are
`_REASONS` in `src/attachments/_overview.py`; `meta.extra` holds the
numbers. The limit line is also a warning of the overview.

### Archives

`.zip`, `.tar`, `.tgz`, `.tar.gz`, `.tbz2`, `.tar.bz2`, `.txz`, `.tar.xz`
(by name, any case). Zip-based documents (`.docx`, `.xlsx`, …) are never
expanded. Members are listed in the archive's order (a zip's central
directory); folders and, in tar, everything that is not a regular file are
left out; names have `\` turned into `/` and empty, `.` and `..` segments
and leading `/` removed. A member that is itself an archive by name and by
content is expanded in place, up to 8 levels. The whole expansion stops at
1 GiB uncompressed (`ATT_MAX_EXPANSION_BYTES`), an `unpack-error`. Bytes
named as an archive that are neither zip nor tar become one member named
`blob`. Zip names are UTF-8 when their flag says so, else code page 437.

*Extension `archive/bz2-xz`* (a declared extension: a case that
`requires` it is skipped by an implementation without it, which must
instead refuse it with `unpack-error`): `.tar.bz2`, `.tbz2`, `.tar.xz`, `.txz`. An
implementation without it gives an `unpack-error` that says so (and the
service is not asked: the archive is local). Python has it; TypeScript
does not yet.

### Downloads

One GET, redirects followed (at most 10), a `User-Agent` of
`attachments-unpack/1.0 (+https://github.com/MaximeRivest/att)`
(`ATT_USER_AGENT`), 60 s timeout, no `Accept-Encoding`. Over 256 MiB
(`ATT_MAX_DOWNLOAD_BYTES`; a declared `Content-Length` over it fails before
reading) is an `unpack-error`. With private addresses blocked
(`ATT_BLOCK_PRIVATE_URLS`, a setting, or the server), the address and
every redirect must resolve only to public addresses.

The file's name: `Content-Disposition`'s `filename*` (after `''`,
percent-decoded) or `filename`, else the final address's last path
segment, percent-decoded (`index` when empty and the type is listed
below, else `download`), sanitized like an archive member name. Then made
to agree with the declared `Content-Type` (`_TYPE_EXTENSIONS` in
`src/attachments/_sources/http.py`): when the type is listed and the name
does not end with an agreeing extension, the type's extension is appended
(`README.md` served as HTML is `README.md.html`), with a warning when the
name had a real extension that is not a server-built page's. The artifact's
`meta.source` is the final address.

## Routing a file

**Which processor.** The file name's extension (lowercased) if a
processor is registered for it; else the extension sniffed from the
content, if a processor is registered for that; else, if the bytes look
like text, the text processor (key `__text__`); else none. Option warnings
name the extension, or `text` for the text processor.

**Sniffing** (`detect_extension`): `%PDF-` → `.pdf`; `\x89PNG` → `.png`;
`FF D8 FF` → `.jpg`; `GIF87a`/`GIF89a` → `.gif`; `RIFF`…`WEBP` → `.webp`;
`BM` with at least 26 bytes whose little-endian size at 2 is 0 or the
length → `.bmp`; `PK\x03\x04` with a `[Content_Types].xml` member and a
member under `word/`, `xl/` or `ppt/` → `.docx`, `.xlsx`, `.pptx`; after a
UTF-8 BOM and white space, `<!doctype html` or `<html` (any case) →
`.html`; else none.

**Looks like text**: empty, or no NUL byte and fewer than 5% of bytes
outside {7, 8, 9, 10, 12, 13, 27, 32–255}.

**Named processors** and the `processor` option: as in
[IR-CONTRACT.md](IR-CONTRACT.md#routing-contract-corepy).

**Local or service**, by `prefer`:

| mode | |
|---|---|
| `local` (default) | the local processor; if its result lacks a dependency (`lacks_dependency`) and the service is configured, the service. If the service fails and the local result had its text, that result, with the warning `The service could not make the missing part either: <message>`. No processor and a service: the service. No processor, no service: an empty artifact with note `no processor available`. |
| `service` | the service first; if it fails, local as above (note `no processor available` when there is none) |
| `local-only` | local only; no processor: note `no local processor available` |
| `service-only` | the service; not configured: error `service-error` |

A local processor that throws gives `missing-dependency` for a missing
module (message naming what to install) and `processing-error` otherwise;
it is then routed as that artifact (a crash is final: the file is not
sent to the service for it).
A service answer gets `meta.via = "service"`; a failed service call is an
artifact with error `service-error`.

**The service is configured** only when an API key or a service address
was set (`configure`, the environment `ATTACHMENTS_API_KEY`,
`ATTACHMENTS_SERVICE_URL`). The default address alone never counts: no
file is sent anywhere unless asked.

**After processing**: the artifact gets every required key, `meta.source`
when absent (the file's name); a download's `meta.source` is its final
address; source warnings and dropped folder options go to
`meta.warnings`.

## The text processor

Decodes UTF-8 (a BOM is kept as U+FEFF), else Latin-1 (which decodes any
bytes). `meta.kind` is `text`; `meta.extra` is
`{"encoding": "utf-8"|"latin-1", "chars": <code points>, "filename": <name>}`.
It takes no options. Extensions: `.txt .md .markdown .rst .json .yaml
.yml .toml .ini .cfg .log .py .java .js .ts .css .xml .tex`, and the text
fallback.

## Settings

`configure(...)` sets them for the process; the environment overrides
`configure`: `ATTACHMENTS_API_KEY`, `ATTACHMENTS_SERVICE_URL`
(default `https://api.attachments.dev/v1`), `ATTACHMENTS_PREFER`
(`local`, `service`, `local-only`, `service-only`; anything else is
refused), `ATTACHMENTS_TIMEOUT` (seconds, default 130). A call's own
settings win over both.

## Prompt mentions (`from_prompt`)

A mention is text in backticks, straight or curly double quotes, or
single quotes not inside a word (it may name a folder); an `http(s)://`
address (trailing `.,;:!?` and an unbalanced `)` removed; fetched only
with `urls`); or a bare word with an extension of 1 to 10 letters or
digits, not inside a word, an e-mail or a longer path and ending its word
(not followed by a word character, `-` or `@`), optionally followed by
`[options]` (a trailing `.` removed). Quoted text inside an unclosed `[`
on its line is an option value, not a mention. Earlier kinds take their text
first; results are in order of appearance, duplicates (same file, same
options) once. A mention is attached only if it exists inside a root
folder (default: the current folder; no `~`, no way out by `..` or links),
and never if it looks like a secret by name or content. Its `meta.source`
is the text the prompt used. "Word" characters are letters, digits and
`_` in Unicode.
