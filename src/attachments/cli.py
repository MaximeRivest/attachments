#!/usr/bin/env python3
"""attachments CLI (`att` / `attachments`).

Usage:
    att [OPTIONS] [INPUT ...]

Examples:
    att README.md
    att report.pdf --pages 1-4
    att report.pdf[pages:1-4] data.xlsx[sheet:Sales,rows:50]
    att . --json
    att README.md --copy --prompt "Summarize this"
    att --options          # list every declared DSL option
    att --options .pdf     # options for one processor

Notes:
    - Unknown `--key value` options are converted to DSL options: `[key:value]`.
    - Control options are: `--copy`, `--clipboard`, `--verbose`, `--json`,
      `--prefer`, `--api-key`, `--prompt`, `--options`, `--help`.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import sys
from typing import Any

from . import att

_CONTROL_KEYS = {
    "h",
    "help",
    "c",
    "y",
    "copy",
    "clipboard",
    "v",
    "verbose",
    "json",
    "prefer",
    "api-key",
    "prompt",
    "options",
}


def _resolve_path(path: str) -> str:
    if path in {".", "./"}:
        return os.getcwd()
    return path


def _extract_dsl_from_path(path: str) -> tuple[str, str]:
    match = re.search(r"^([^\[]+)(\[.+\])$", path)
    if match:
        return match.group(1), match.group(2)
    return path, ""


def _add_option_value(opts: dict[str, str | list[str]], key: str, value: str) -> None:
    if key in opts:
        if isinstance(opts[key], list):
            opts[key].append(value)
        else:
            opts[key] = [opts[key], value]
    else:
        opts[key] = value


def _parse_mixed_args(args: list[str]) -> tuple[list[str], dict[str, str | list[str]]]:
    paths: list[str] = []
    opts: dict[str, str | list[str]] = {}

    i = 0
    while i < len(args):
        arg = args[i]

        if arg.startswith("-"):
            key = arg.lstrip("-")
            if "=" in key:
                key, value = key.split("=", 1)
                _add_option_value(opts, key, value)
            elif key in {"c", "y", "copy", "clipboard"}:
                opts["copy"] = "true"
            elif key in {"v", "verbose"}:
                opts["verbose"] = "true"
            elif key in {"json"}:
                opts["json"] = "true"
            elif i + 1 < len(args) and not args[i + 1].startswith("-"):
                _add_option_value(opts, key, args[i + 1])
                i += 1
            else:
                opts[key] = "true"
        else:
            paths.append(arg)

        i += 1

    return paths, opts


def _build_dsl_from_options(opts: dict[str, str | list[str]]) -> str:
    parts: list[str] = []
    for key, value in opts.items():
        if key in _CONTROL_KEYS:
            continue
        if isinstance(value, list):
            parts.append(f"[{key}:{','.join(str(v) for v in value)}]")
        else:
            parts.append(f"[{key}:{value}]")
    return "".join(parts)


def _artifact_to_json_safe(obj: Any) -> Any:
    if isinstance(obj, bytes):
        return base64.b64encode(obj).decode("ascii")
    if isinstance(obj, list):
        return [_artifact_to_json_safe(v) for v in obj]
    if isinstance(obj, dict):
        return {k: _artifact_to_json_safe(v) for k, v in obj.items()}
    return obj


def _render_text(artifacts: list[dict[str, Any]]) -> str:
    chunks: list[str] = []
    for a in artifacts:
        text = a.get("text", "")
        if text and text.strip():
            chunks.append(text)
    return "\n\n".join(chunks)


def _format_errors(artifacts: list[dict[str, Any]]) -> list[str]:
    """Render meta.error entries as human-readable lines."""
    lines: list[str] = []
    for a in artifacts:
        meta = a.get("meta", {})
        error = meta.get("error")
        if error:
            source = meta.get("source", "?")
            code = error.get("code", "error")
            message = error.get("message", "")
            lines.append(f"{source}: [{code}] {message}")
    return lines


def _copy_to_clipboard(text: str) -> None:
    try:
        import pyperclip
    except ImportError as e:
        raise RuntimeError(
            "Clipboard support requires pyperclip. Install with: pip install pyperclip"
        ) from e
    pyperclip.copy(text)


def _print_help() -> None:
    print(__doc__ or "att command")


def _format_option_rows(entries: list[dict[str, Any]]) -> list[str]:
    """Render one schema's option dicts as aligned table rows."""
    if not entries:
        return ["  (no options)"]
    rows: list[str] = []
    for opt in entries:
        aliases = ", ".join(opt["aliases"])
        name = opt["name"] + (f" ({aliases})" if aliases else "")
        detail = opt["help"]
        if opt["example"]:
            detail += f"  e.g. [{opt['example']}]"
        rows.append(f"  {name:<24} {opt['type']:<12} {detail.strip()}")
    return rows


def _print_options(key: str | None) -> int:
    """Print the declared DSL option table (generated from dsl_schema())."""
    from .options import dsl_schema

    schema = dsl_schema()
    sections = {**schema["processors"], **schema["sources"]}

    if key is not None:
        if not key.startswith((".", "__")) and "://" not in key:
            key = "." + key
        entries = sections.get(key.lower() if "://" not in key else key)
        if entries is None:
            print(f"No options registered for {key!r}", file=sys.stderr)
            return 1
        sections = {key: entries}

    for section_key, entries in sections.items():
        if key is None and not entries:
            continue  # keep the full listing focused on processors w/ options
        print(section_key)
        for row in _format_option_rows(entries):
            print(row)
        print()
    return 0


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv

    if not args or any(a in {"-h", "--help", "help"} for a in args):
        _print_help()
        return 0

    paths, opts = _parse_mixed_args(args)

    if "options" in opts:
        value = opts["options"]
        key = value if isinstance(value, str) and value != "true" else None
        return _print_options(key)

    if not paths:
        print("Error: no input paths provided", file=sys.stderr)
        print("Tip: use '.' for current directory", file=sys.stderr)
        return 1

    verbose = opts.get("verbose", "false") == "true"
    want_json = opts.get("json", "false") == "true"
    want_copy = opts.get("copy", "false") == "true"

    prefer = opts.get("prefer") if isinstance(opts.get("prefer"), str) else None
    api_key = opts.get("api-key") if isinstance(opts.get("api-key"), str) else None
    prompt = opts.get("prompt") if isinstance(opts.get("prompt"), str) else ""

    if verbose:
        logging.basicConfig(level=logging.DEBUG)

    dsl_from_opts = _build_dsl_from_options(opts)

    expanded_inputs: list[str] = []
    for path in paths:
        resolved = _resolve_path(path)
        clean, embedded_dsl = _extract_dsl_from_path(resolved)
        expanded_inputs.append(clean + embedded_dsl + dsl_from_opts)

    all_artifacts: list[dict[str, Any]] = []

    try:
        for input_item in expanded_inputs:
            all_artifacts.extend(att(input_item, api_key=api_key, prefer=prefer))
    except Exception as exc:  # noqa: BLE001
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if want_json:
        print(json.dumps(_artifact_to_json_safe(all_artifacts), indent=2))
        return 0

    # Surface typed errors (meta.error.code/message) on stderr
    for line in _format_errors(all_artifacts):
        print(f"Error: {line}", file=sys.stderr)

    output_text = _render_text(all_artifacts)

    if want_copy:
        clipboard_text = f"{prompt}\n\n{output_text}" if prompt else output_text
        try:
            _copy_to_clipboard(clipboard_text)
            print("Copied to clipboard.")
            return 0
        except Exception as exc:  # noqa: BLE001
            print(f"Error: {exc}", file=sys.stderr)
            return 1

    print(output_text)
    return 0


def app() -> None:
    raise SystemExit(main())


if __name__ == "__main__":
    app()
