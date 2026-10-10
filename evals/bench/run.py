#!/usr/bin/env python3
"""How well do coding agents use attachments (with lm15, MCP and the CLI)?

20 tasks (tasks.py), each given to a fresh Pi agent in a fresh workspace,
graded by code. The agents differ only in their model; every agent gets the
same two skills (attachments' own, and lm15's from https://lm15.dev/skill.md).

    uv run python evals/bench/run.py --check             # graders vs expert/naive
    uv run python evals/bench/run.py --reps 3 --parallel 6
    uv run python evals/bench/run.py --tasks cache rag --models openai-codex/gpt-6-luna --reps 1
    uv run python evals/bench/run.py --report evals/bench/runs/<stamp>

Workspaces stay in ~/.cache/attachments-bench/<stamp>/; results (grades,
agent metrics, Pi sessions) go to evals/bench/runs/<stamp>/.
"""

from __future__ import annotations

import argparse
import concurrent.futures as futures
import functools
import http.server
import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
import tasks as T  # noqa: E402

CACHE = Path.home() / ".cache" / "attachments-bench"
SKILL = REPO / "src" / "attachments" / "skill"
LM15_SKILL = Path.home() / "Projects" / "lm15-dev" / "website" / "public" / "skill.md"
MODELS = ("openai-codex/gpt-6-luna", "openai-codex/gpt-6.1-sol")
EXTRAS = "pdf,image,docx,xlsx,pptx,html,ocr,mcp,lm15"

RULES = (
    "You are working in the current folder for a user who will read your final "
    "message. Do not open, list or search anything under ~/Projects or "
    "~/.cache/attachments-bench outside the current folder. Finish the task "
    "completely, then reply with a short summary."
)
FORBIDDEN = re.compile(r"Projects/(attachments|lm15)")


def forbidden(args: str, work: Path) -> bool:
    """The sources, or another run's files (its own folder and the skills are fine)."""
    if FORBIDDEN.search(args):
        return True
    others = args.replace(str(work), "")
    return "attachments-bench/" in others and "/skills/" not in others


MCP_TOOLS = "read,write,mcp__attachments__att,mcp__attachments__att_options"


def _env() -> dict:
    return {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}


# =============================================================================
# The local web site (tasks web, cli_web)
# =============================================================================


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def start_site() -> str:
    root = CACHE / "site"
    shutil.rmtree(root, ignore_errors=True)
    T.build_site(root)
    handler = functools.partial(_Quiet, directory=str(root))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{server.server_address[1]}"


# =============================================================================
# Workspaces
# =============================================================================


def build_wheel() -> Path:
    out = CACHE / "wheel"
    shutil.rmtree(out, ignore_errors=True)
    subprocess.run(
        ["uv", "build", "-q", "--wheel", "--out-dir", str(out)], cwd=REPO, check=True
    )
    return next(out.glob("*.whl"))


def build_venv(work: Path, wheel: Path) -> None:
    subprocess.run(
        ["uv", "venv", "-q", "--python", "3.12", str(work / ".venv")],
        check=True,
        env=_env(),
    )
    subprocess.run(
        [
            "uv",
            "pip",
            "install",
            "-q",
            "--python",
            str(work / ".venv" / "bin" / "python"),
            f"attachments[{EXTRAS}] @ {wheel.as_uri()}",
        ],
        check=True,
        env=_env(),
    )


def workspace(name: str, work: Path, wheel: Path) -> None:
    task = T.TASKS[name]
    work.mkdir(parents=True, exist_ok=True)
    task.build(work)
    if task.venv:
        build_venv(work, wheel)
    if task.mcp:
        (work / ".pi").mkdir()
        (work / ".pi" / "mcp.json").write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "attachments": {
                            "command": str(work / ".venv" / "bin" / "attachments-mcp"),
                            "exposure": "direct",
                            "description": "Read any file (PDF, Office, images, folders, URLs) as text and pictures",
                        }
                    }
                }
            )
        )


def prompt(name: str, site: str) -> str:
    return T.TASKS[name].prompt.replace("{site}", site)


# =============================================================================
# Grading
# =============================================================================


def grade(name: str, work: Path) -> dict:
    task = T.TASKS[name]
    if task.grader is None:
        return T.skill_eval.grade(name, work)
    cmd = [str(work / ".venv" / "bin" / "python"), "-c", T.PRELUDE + task.grader]
    p = None
    try:
        p = subprocess.run(
            cmd, cwd=work, capture_output=True, text=True, env=_env(), timeout=900
        )
        checks = json.loads(p.stdout.strip().splitlines()[-1])
    except Exception as exc:
        tail = p.stderr[-800:] if p else ""
        return {
            "success": False,
            "score": 0.0,
            "checks": {},
            "error": f"{exc!r} {tail}",
        }
    required = {
        k: v
        for k, v in checks.items()
        if isinstance(v, bool) and not k.startswith("info")
    }
    score = sum(required.values()) / len(required) if required else 0.0
    return {"success": score == 1.0, "score": round(score, 2), "checks": checks}


def apply_solution(name: str, work: Path, files: dict, wheel: Path, site: str) -> None:
    for fname, body in files.items():
        if fname.startswith("__"):
            continue
        text = textwrap.dedent(body).lstrip().replace("{site}", site)
        (work / fname).write_text(text)
    for cmd in files.get("__setup__", []):
        cmd = [part.format(wheel=wheel.as_uri()) for part in cmd]
        subprocess.run(cmd, cwd=work, check=True, env=_env())
    if "__run__" in files:
        args = [a.replace("{site}", site) for a in files["__run__"]]
        subprocess.run(
            [str(work / ".venv" / "bin" / "python"), *args],
            cwd=work,
            env=_env(),
            timeout=900,
        )
    if "__run__sh__" in files:
        subprocess.run(
            ["bash", *files["__run__sh__"]], cwd=work, env=_env(), timeout=300
        )


def check(names: list[str], wheel: Path, site: str) -> int:
    """Expert solutions must score 1.0 and naive ones less: the graders work."""
    root = CACHE / "check"
    shutil.rmtree(root, ignore_errors=True)

    def one(job):
        label, name = job
        task = T.TASKS[name]
        work = root / label / name / "work"
        workspace(name, work, wheel)
        apply_solution(
            name, work, task.expert if label == "expert" else task.naive, wheel, site
        )
        return label, name, grade(name, work)

    jobs = [(label, n) for n in names for label in ("expert", "naive")]
    failed = False
    with futures.ThreadPoolExecutor(8) as pool:
        for label, name, g in pool.map(one, jobs):
            ok = g["success"] is (label == "expert")
            note = ""
            if not ok and label == "naive" and T.TASKS[name].naive_may_pass:
                ok, note = True, f"  (allowed: {T.TASKS[name].naive_may_pass})"
            failed |= not ok
            shown = {k: v for k, v in g["checks"].items()} or g.get("error")
            print(
                f"{label:6} {name:13} {g['score']:.2f} {'ok' if ok else 'WRONG'}  {shown}{note}",
                flush=True,
            )
    return 1 if failed else 0


# =============================================================================
# Running agents
# =============================================================================


def session_metrics(session_dir: Path, work: Path) -> dict:
    m = dict(
        cost=0.0,
        turns=0,
        tool_calls=0,
        tool_errors=0,
        read_skills=[],
        used_mcp=False,
        contaminated=False,
        final="",
        error=None,
    )
    for f in sorted(session_dir.glob("*.jsonl")):
        for line in f.read_text().splitlines():
            try:
                o = json.loads(line)
            except json.JSONDecodeError:
                continue
            if o.get("type") != "message":
                continue
            msg = o["message"]
            if msg.get("role") == "assistant":
                m["turns"] += 1
                m["cost"] += ((msg.get("usage") or {}).get("cost") or {}).get(
                    "total", 0
                ) or 0
                m["error"] = msg.get("errorMessage") or m["error"]
                for c in msg.get("content") or []:
                    if c.get("type") == "toolCall":
                        m["tool_calls"] += 1
                        args = json.dumps(c.get("arguments"))
                        for skill in ("attachments", "lm15"):
                            if (
                                f"skills/{skill}" in args
                                and skill not in m["read_skills"]
                            ):
                                m["read_skills"].append(skill)
                        if c.get("name", "").startswith("mcp__attachments__att"):
                            m["used_mcp"] = True
                        if forbidden(args, work):
                            m["contaminated"] = True
                    elif c.get("type") == "text":
                        m["final"] = c.get("text", "")
            elif msg.get("role") == "toolResult":
                text = " ".join(
                    c.get("text", "")
                    for c in msg.get("content") or []
                    if isinstance(c, dict)
                )
                if msg.get("isError") or re.search(
                    r"Traceback \(most recent|exited with code [1-9]", text
                ):
                    m["tool_errors"] += 1
    m["cost"] = round(m["cost"], 4)
    return m


def one(
    name: str,
    model: str,
    rep: int,
    run_root: Path,
    results: Path,
    args,
    wheel: Path,
    site: str,
) -> dict:
    slug = model.split("/", 1)[1]
    base = run_root / name / f"{slug}-{rep}"
    work = base / "work"
    workspace(name, work, wheel)
    provider, model_id = model.split("/", 1)
    task = T.TASKS[name]
    cmd = [
        "pi",
        "-p",
        "--mode",
        "json",
        "--no-extensions",
        "--no-skills",
        "--no-context-files",
        "--no-prompt-templates",
        "--no-themes",
        "--session-dir",
        str(base / "session"),
        "--provider",
        provider,
        "--model",
        model_id,
        "--thinking",
        args.thinking,
        "--append-system-prompt",
        RULES,
        "--skill",
        str(run_root / "skills" / "attachments"),
        "--skill",
        str(run_root / "skills" / "lm15"),
    ]
    if task.mcp:
        cmd += ["-e", "builtin:mcp", "--approve", "--tools", MCP_TOOLS]
    cmd.append(prompt(name, site))
    started = time.time()
    try:
        p = subprocess.run(
            cmd,
            cwd=work,
            env=_env(),
            capture_output=True,
            text=True,
            timeout=args.timeout,
        )
        status = "ok" if p.returncode == 0 else f"exit {p.returncode}"
    except subprocess.TimeoutExpired:
        status = "timeout"
    seconds = round(time.time() - started)
    metrics = session_metrics(base / "session", work)
    graded = grade(name, work)
    if task.mcp:
        graded["checks"]["used_attachments_mcp"] = metrics["used_mcp"]
        graded["success"] = graded["success"] and metrics["used_mcp"]
    result = {
        "task": name,
        "model": model,
        "rep": rep,
        "status": status,
        "seconds": seconds,
        "agent": metrics,
        "grade": graded,
        "work": str(work),
    }
    out = results / name / f"{slug}-{rep}"
    out.mkdir(parents=True, exist_ok=True)
    (out / "result.json").write_text(json.dumps(result, indent=1))
    for f in (base / "session").glob("*.jsonl"):
        shutil.copy(f, out / "session.jsonl")
    misses = {k: v for k, v in graded["checks"].items() if v is False}
    print(
        f"{name:13} {slug:12} #{rep}  {'✓' if graded['success'] else '✗'} {graded['score']:.2f}"
        f"  {seconds:4d}s  {metrics['tool_calls']:3d} tools ({metrics['tool_errors']} failed)"
        f"  skills read: {','.join(metrics['read_skills']) or '-'}"
        f"{'  CONTAMINATED' if metrics['contaminated'] else ''}  {status}"
        f"  {misses or ''}{'  ' + graded['error'][:200] if graded.get('error') else ''}",
        flush=True,
    )
    return result


# =============================================================================
# Report
# =============================================================================


def report(results: Path) -> str:
    rows = [json.loads(p.read_text()) for p in sorted(results.glob("*/*/result.json"))]
    models = sorted({r["model"] for r in rows})
    short = {m: m.split("/", 1)[1] for m in models}
    lines = [
        "| task | " + " | ".join(short[m] for m in models) + " | what went wrong |",
        "|---|" + "---|" * len(models) + "---|",
    ]
    totals = {m: [0, 0] for m in models}
    for name in T.TASKS:
        cells, misses = [], {}
        for m in models:
            rs = [
                r
                for r in rows
                if r["task"] == name
                and r["model"] == m
                and not r["agent"]["contaminated"]
            ]
            if not rs:
                cells.append("—")
                continue
            wins = sum(r["grade"]["success"] for r in rs)
            totals[m][0] += wins
            totals[m][1] += len(rs)
            secs = sorted(r["seconds"] for r in rs)[len(rs) // 2]
            cells.append(f"{wins}/{len(rs)} ({secs}s)")
            for r in rs:
                for k, v in r["grade"]["checks"].items():
                    if v is False and not k.startswith("info"):
                        key = f"{k} ({short[m]})"
                        misses[key] = misses.get(key, 0) + 1
                if r["grade"].get("error"):
                    key = f"grader error ({short[m]})"
                    misses[key] = misses.get(key, 0) + 1
        missed = ", ".join(f"{k} ×{n}" for k, n in sorted(misses.items())) or "—"
        lines.append(f"| {name} | " + " | ".join(cells) + f" | {missed} |")
    lines.append(
        "| **total** | "
        + " | ".join(f"**{w}/{n}**" for w, n in (totals[m] for m in models))
        + " | |"
    )
    for m in models:
        rs = [r for r in rows if r["model"] == m]
        if rs:
            secs = sorted(r["seconds"] for r in rs)[len(rs) // 2]
            tools = sum(r["agent"]["tool_calls"] for r in rs) / len(rs)
            read = {
                s: sum(s in r["agent"]["read_skills"] for r in rs)
                for s in ("attachments", "lm15")
            }
            lines.append(
                f"\n{short[m]}: median {secs}s, {tools:.1f} tool calls a run; read the "
                f"attachments skill in {read['attachments']}/{len(rs)} runs, lm15's in "
                f"{read['lm15']}/{len(rs)}."
            )
    dirty = [
        f"{r['task']}/{short[r['model']]}-{r['rep']}"
        for r in rows
        if r["agent"]["contaminated"]
    ]
    if dirty:
        lines.append(f"\nLeft out (looked at forbidden files): {', '.join(dirty)}")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--tasks", nargs="+", default=list(T.TASKS), choices=list(T.TASKS))
    ap.add_argument("--models", nargs="+", default=list(MODELS))
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--parallel", type=int, default=6)
    ap.add_argument("--thinking", default="medium")
    ap.add_argument("--timeout", type=int, default=1200)
    ap.add_argument(
        "--check", action="store_true", help="grade expert and naive solutions only"
    )
    ap.add_argument("--report", type=Path, help="print the table of an earlier run")
    ap.add_argument(
        "--rescan",
        type=Path,
        help="recompute agent metrics of an earlier run from its sessions",
    )
    args = ap.parse_args()
    if args.report:
        print(report(args.report.resolve()))
        return 0
    if args.rescan:
        for path in sorted(args.rescan.resolve().glob("*/*/result.json")):
            r = json.loads(path.read_text())
            r["agent"] = session_metrics(path.parent, Path(r["work"]))
            path.write_text(json.dumps(r, indent=1))
        print(report(args.rescan.resolve()))
        return 0
    wheel = build_wheel()
    site = start_site()
    if args.check:
        return check(args.tasks, wheel, site)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    run_root, results = CACHE / stamp, HERE / "runs" / stamp
    shutil.copytree(
        SKILL,
        run_root / "skills" / "attachments",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    (run_root / "skills" / "lm15").mkdir(parents=True)
    shutil.copy(LM15_SKILL, run_root / "skills" / "lm15" / "SKILL.md")
    results.mkdir(parents=True)
    (results / "setup.json").write_text(
        json.dumps(
            {
                "models": args.models,
                "thinking": args.thinking,
                "reps": args.reps,
                "task_model": T.TASK_MODEL,
                "commit": subprocess.run(
                    ["git", "-C", str(REPO), "rev-parse", "HEAD"],
                    capture_output=True,
                    text=True,
                ).stdout.strip(),
                "lm15_skill": str(LM15_SKILL),
            },
            indent=1,
        )
    )
    jobs = [
        (t, m, r)
        for r in range(1, args.reps + 1)
        for t in args.tasks
        for m in args.models
    ]
    with futures.ThreadPoolExecutor(args.parallel) as pool:
        list(pool.map(lambda j: one(*j, run_root, results, args, wheel, site), jobs))
    table = report(results)
    (results / "report.md").write_text(table)
    print("\n" + table)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
