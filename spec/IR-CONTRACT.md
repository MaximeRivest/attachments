# Artifact IR Contract (v1) — binding for all code in this repo

This is the frozen intermediate representation every processor produces, every
consumer accepts, and the server transports. Code and tests must conform.
(Epic B of VISION.md. JSON Schema lives in spec/artifact.schema.json.)

## Shape

```python
Artifact = {
    "text": str,                  # required, may be ""
    "images": list[ImageItem],    # required, may be []
    "audio": list[dict],          # required, reserved
    "video": list[dict],          # required, reserved
    "meta": Meta,                 # required
}

ImageItem = {
    "name": str,                  # required, e.g. "doc-page-1.png"
    "mimetype": str,              # required, e.g. "image/png"
    "bytes": bytes,               # required in-process
    "bytes_b64": str,             # wire transport only (JSON); never both on output
    "page": int,                  # optional, 1-based source page/slide
}

Meta = {
    "source": str,                # required after normalization (core sets it)
    "kind": str,                  # optional: "text"|"pdf"|"table"|"document"|"html"|"slides"|"image"|...
    "via": str,                   # optional: "service" when processed remotely (absent = local)
    "error": {                    # optional; present only on failure
        "code": str,              # one of ERROR CODES below
        "message": str,           # human-readable, includes remedy when known
    },
    "note": str,                  # optional informational message
    "warnings": list[str],        # optional, e.g. DSL unknown-option warnings
    "segments": list[Segment],    # optional structural segmentation
    "extra": dict,                # optional processor-specific freeform metadata
}

Segment = {
    "kind": str,                  # "page"|"sheet"|"slide"|"section"
    "label": str,                 # "page 1", "Sales", "Q3 Review"
    "start": int,                 # offset into artifact["text"] (inclusive)
    "end": int,                   # offset into artifact["text"] (exclusive)
}
```

Rules:
- Keys outside this shape are forbidden at the top level and inside `meta`
  (processor-specific data goes in `meta.extra`).
- Optional meta keys are ABSENT when not applicable, never None.
- `meta.error.message` for missing deps must include the pip install remedy.

## Error codes (constants in `attachments.types`)

| Constant                  | Value                 | Meaning |
|---------------------------|-----------------------|---------|
| `ERROR_MISSING_DEPENDENCY`| `missing-dependency`  | Optional dep not installed — DRIVES SERVICE FALLBACK |
| `ERROR_PASSWORD_REQUIRED` | `password-required`   | Encrypted file, wrong/missing password |
| `ERROR_PARSE`             | `parse-error`         | File exists but could not be parsed |
| `ERROR_UNPACK`            | `unpack-error`        | Source could not be resolved/fetched |
| `ERROR_SERVICE`           | `service-error`       | Remote service failed |
| `ERROR_INVALID_OPTION`    | `invalid-option`      | Option value invalid for this processor |
| `ERROR_PROCESSING`        | `processing-error`    | Anything else |

## Helper API (`attachments.types`)

- `make_artifact(*, text="", images=None, audio=None, video=None, meta=None) -> Artifact`
- `error_artifact(source, code, message) -> Artifact`
- `missing_dep_artifact(source, feature) -> Artifact` — looks up the install
  hint from `deps.DEPENDENCY_MAP`, sets code `missing-dependency`
- `is_missing_dependency(artifact) -> bool` — typed check; the ONLY way core
  routing may decide to fall back to the service. String-matching error
  messages is forbidden.
- `normalize_artifact(artifact, source) -> Artifact` — fills required keys,
  sets `meta.source` if absent.

## Processor contract

A processor is a pure function `(data: bytes, *, filename=None, **options) -> Artifact`.
- Never raises for missing optional deps — returns `missing_dep_artifact(...)`.
- Never raises for bad input — returns `error_artifact(...)`.
- Sets `meta.kind`; puts backend details, counts, etc. in `meta.extra`.
- Population of `meta.segments` (offsets into `text`) is required for
  multi-part formats: pdf (pages), xlsx (sheets), pptx (slides).

## Routing contract (core.py)

- Local result with `is_missing_dependency(result)` and an API key configured
  → try service.
- Service results get `meta.via = "service"`.
- No processor for extension and not text → empty artifact with
  `meta.note = "no processor available"` (not an error).
- Errors NEVER raise out of `att()`; they come back as error artifacts.

## Wire format (service.py / server.py)

- JSON transport replaces each image's `bytes` with `bytes_b64` (standard
  base64); the client decodes back to `bytes` and removes `bytes_b64`.
- The server response body is exactly an Artifact (with `bytes_b64` images).
- `meta` passes through transport unchanged (minus image encoding).

## The word "flags" must not appear in code

The legacy `flags` key is renamed to `meta` everywhere — code, tests,
docstrings, docs. Grep for `flags` must return zero hits in src/ and tests/.
