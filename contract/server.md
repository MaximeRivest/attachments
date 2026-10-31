# The server's API (v1)

What a client (any implementation of `att()`) sends to an Attachments
server, and what the server answers. `src/attachments/server.py` is
Python's server; the hosted one at `https://api.attachments.dev/v1` runs
it. Every route answers JSON. A path may start with `/v1` (it is
removed), so a client configured with either `https://host` or
`https://host/v1` reaches the same routes.

## Authentication

When the server has a key (`ATTACHMENTS_SERVER_KEY`), every `POST` needs
`Authorization: Bearer <key>`; otherwise `401 {"error": "Unauthorized"}`.
`GET` routes are open. A client sends the header only when it has a key.

## Errors

Any failure that is the request's: `4xx {"error": "<message>"}`, the
message safe to show. A failure of the server: `500 {"error": "Internal
error"}`. `404 {"error": "Not found"}` for other paths. A request body
over the server's upload limit (`ATTACHMENTS_MAX_UPLOAD`, default 256 MiB)
is `413`.

## `POST /process`: one file, one artifact

**An upload**: `multipart/form-data` with one part `file` (its
`filename` names the file; routing uses it) and one part per option,
whose value is the option's JSON (`"1-4"`, `300`, `true`). The server
reads the file `local-only` with those options exactly as `att()` reads a
local file with options from the call, and answers `200` with one
Artifact in wire form ([artifact.schema.json](artifact.schema.json)).
A file the server cannot read is still `200`: the Artifact carries
`meta.error`.

**A web address**: `application/json`, `{"url": "https://…", "options":
{…}}`. The server downloads it as `att(url, **options)` does (private
addresses blocked, downloads capped at the upload limit) and answers with
one Artifact. A repository root, or an address holding several files, is
`400` (use `/unpack`).

**What a client sends.** A client sends the file's bytes and name as it
would read them, and its options as given (from the string and the call,
the call's winning), with text options as written
([reading.md](reading.md#options)); folder, source and `processor`
options are left out, and `watermark` too when the client draws labels
itself (Python does; TypeScript sends it and the server draws them), and
a download's address is added as `url` when the format declares that
option and the call set none. Option values that are null are not sent.

**What a client does with the answer.** `200`: the body is an Artifact;
it is checked like `from_wire`, gets `meta.via = "service"`, and is the
result. Anything that is not a valid Artifact is a `service-error`. `401`:
`service-error` "Invalid API key"; `402`: "API quota exceeded"; `413`:
"File too large for service"; other `4xx`/`5xx`: "Service error:
<error>"; no answer within the timeout, or no connection: `service-error`
naming it.

## `POST /unpack`: the files at an address, or in an archive

`application/json` `{"url": "<http(s) or github:// address>"}`, or an
uploaded archive (`multipart/form-data`, part `file`). Answers `200
{"files": [{"filename", "data_b64"}, …]}` in order. A client uses it only
when its own source failed for an address.

## `GET /health`, `GET /formats`, `GET /options`

`/health`: `{"status": "ok", "version", "features": {name: true, …}}` (the
features the server has). `/formats`: `{"formats": [keys], "count"}`.
`/options`: the option schema, as [dsl-schema.json](dsl-schema.json).
