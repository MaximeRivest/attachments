"""Start `attachments-mcp` and talk to it over stdio, as an agent would.

Used by the release workflow on the built package with freshly resolved
dependencies: unit tests use the locked SDK, users get the newest one.

    python scripts/check_mcp_stdio.py /path/to/venv/bin/attachments-mcp

Standard library only. Exits non-zero, with the server's stderr, on failure.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


def main(command: str) -> int:
    with tempfile.TemporaryDirectory() as tmp:
        note = Path(tmp) / "note.md"
        note.write_text("Release check: the MCP server reads files.")
        requests = [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "release-check", "version": "1"},
                },
            },
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "att", "arguments": {"source": str(note)}},
            },
        ]
        proc = subprocess.Popen(
            [command],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        assert proc.stdin and proc.stdout
        replies: dict[int, dict] = {}
        try:
            for request in requests:
                proc.stdin.write(json.dumps(request) + "\n")
                proc.stdin.flush()
                if "id" not in request:
                    continue
                while request["id"] not in replies:
                    line = proc.stdout.readline()
                    if not line:
                        raise RuntimeError("server closed its output")
                    message = json.loads(line)
                    if "id" in message:
                        replies[message["id"]] = message
        except Exception as exc:
            proc.kill()
            print(f"FAILED: {exc}\n--- server stderr ---\n{proc.stderr.read()}")
            return 1
        finally:
            proc.stdin.close()
        proc.wait(timeout=30)

    errors = [r["error"] for r in replies.values() if "error" in r]
    tools = sorted(t["name"] for t in replies[2].get("result", {}).get("tools", []))
    content = replies[3].get("result", {}).get("content", [])
    text = "".join(c.get("text", "") for c in content)
    ok = (
        not errors
        and tools == ["att", "att_options"]
        and "the MCP server reads files" in text
    )
    server = replies[1].get("result", {}).get("serverInfo")
    print(f"server={server} tools={tools} errors={errors}")
    print("mcp ok" if ok else f"FAILED: unexpected replies {replies}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
