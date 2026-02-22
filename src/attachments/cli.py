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

Notes:
    - Unknown `--key value` flags are converted to DSL options: `[key:value]`.
    - Control flags are: `--copy`, `--clipboard`, `--verbose`, `--json`,
      `--prefer`, `--api-key`, `--prompt`, `--help`.
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


def _add_flag_value(flags: dict[str, str | list[str]], key: str, value: str) -> None:
    if key in flags:
        if isinstance(flags[key], list):
            flags[key].append(value)
        else:
            flags[key] = [flags[key], value]
    else:
        flags[key] = value


def _parse_mixed_args(args: list[str]) -> tuple[list[str], dict[str, str | list[str]]]:
    paths: list[str] = []
    flags: dict[str, str | list[str]] = {}

    i = 0
    while i < len(args):
        arg = args[i]

        if arg.startswith("-"):
            key = arg.lstrip("-")
            if "=" in key:
                key, value = key.split("=", 1)
                _add_flag_value(flags, key, value)
            elif key in {"c", "y", "copy", "clipboard"}:
                flags["copy"] = "true"
            elif key in {"v", "verbose"}:
                flags["verbose"] = "true"
            elif key in {"json"}:
                flags["json"] = "true"
            elif i + 1 < len(args) and not args[i + 1].startswith("-"):
                _add_flag_value(flags, key, args[i + 1])
                i += 1
            else:
                flags[key] = "true"
        else:
            paths.append(arg)

        i += 1

    return paths, flags


def _build_dsl_from_flags(flags: dict[str, str | list[str]]) -> str:
    parts: list[str] = []
    for key, value in flags.items():
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


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv

    if not args or any(a in {"-h", "--help", "help"} for a in args):
        _print_help()
        return 0

    paths, flags = _parse_mixed_args(args)
    if not paths:
        print("Error: no input paths provided", file=sys.stderr)
        print("Tip: use '.' for current directory", file=sys.stderr)
        return 1

    verbose = flags.get("verbose", "false") == "true"
    want_json = flags.get("json", "false") == "true"
    want_copy = flags.get("copy", "false") == "true"

    prefer = flags.get("prefer") if isinstance(flags.get("prefer"), str) else None
    api_key = flags.get("api-key") if isinstance(flags.get("api-key"), str) else None
    prompt = flags.get("prompt") if isinstance(flags.get("prompt"), str) else ""

    if verbose:
        logging.basicConfig(level=logging.DEBUG)

    dsl_from_flags = _build_dsl_from_flags(flags)

    expanded_inputs: list[str] = []
    for path in paths:
        resolved = _resolve_path(path)
        clean, embedded_dsl = _extract_dsl_from_path(resolved)
        expanded_inputs.append(clean + embedded_dsl + dsl_from_flags)

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
