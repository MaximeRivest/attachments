# Does the skill help coding agents?

`src/attachments/skill/` (shipped in the package; `att --skill --install`)
teaches coding agents to use attachments 1.0. `run.py` measures it: the same
task, in a fresh workspace, given to a fresh Pi agent with the skill and
without it, graded by code.

| task | what the agent must do | the trap |
|---|---|---|
| `photos` | Claude request bodies naming the animal in 6 photos whose file names are the answers | names reach the model (`## cat_1.jpg`) |
| `charts` | OpenAI messages to read bar charts on pages 3-5 of a PDF that has text, pictures ≤ 1600 px | pages with text are not drawn unless `images: true` |
| `folder` | a folder to a reloadable JSON cache; stop, name every unreadable file, write nothing | `att()` never raises; `json.dumps` fails on picture bytes |
| `install` | an empty uv project: print pages 2-3 of a PDF | `uv add attachments` installs 0.25, the old API |
| `scans` | one Claude request reading a 40-page scanned PDF, accepted by Anthropic | the PNG default makes a 126 MB request (limit 32 MB) |

## Fairness

- Both arms: same prompt, model, thinking level; `--no-skills
  --no-extensions --no-context-files`; attachments 1.0 built from this
  checkout and installed in the workspace (except `install`, which starts
  empty). The `none` arm's installed package has its `skill/` folder
  removed, since the skill ships inside it.
- Agents are told not to read `~/Projects/attachments`; a run whose tools
  touched it (or, without the skill, any `SKILL.md`) is reported apart.
- Graders check outcomes, not code style. `--check` runs a hand-written
  expert solution per task (must score 1.0) and a naive one (must fail on
  its trap) before any agent is graded.

## Results (2026-10-07, skill as of this commit)

`openai-codex/gpt-6-astra`, thinking medium, 3 runs per cell:

| task | with skill | without | median time with / without | tool calls with / without |
|---|---|---|---|---|
| photos | 3/3 | 3/3 | 28 s / 29 s | 4 / 4 |
| charts | 3/3 | 3/3 | 31 s / 31 s | 4 / 5 |
| folder | 3/3 | 3/3 | 52 s / 51 s | 5 / 6 |
| install | **3/3** | **0/3** | 30 s / 51 s | 6 / 10 |
| scans | 3/3 | 3/3 | 41 s / 47 s | 4 / 5 |

`openai-codex/gpt-6-luna`, thinking medium, 2 runs per cell:

| task | with skill | without | median time with / without |
|---|---|---|---|
| photos | 2/2 | 2/2 | 10 s / 16 s |
| charts | 2/2 | 2/2 | 21 s / 29 s |
| folder | 2/2 | 2/2 | 47 s / 25 s |
| install | **2/2** | **0/2** | 24 s / 58 s |
| scans | **2/2** | **1/2** | 83 s / 115 s (the miss: a 41 MB request) |

What this says:

- **The decisive help is installing 1.0.** Without the skill every agent
  (5 of 5) ran `uv add attachments`, got 0.25 and wrote its old API; the
  script worked, on the wrong library. With it, 5 of 5 installed 1.0.
- **Elsewhere agents without the skill also succeed**, because 1.0
  documents itself: they read `att`'s docstring or `att.options()` and
  found `sources=False`, `images: true`, `image_format: jpeg`. The skill
  saved a tool call or two and usually some time, and never made a result
  worse. The smaller model missed the 32 MB limit once without it.
- Every agent given the skill read it (the description triggers it).
- An earlier `folder` grader required output identical to `att("docs/")`'s
  defaults and failed agents that rendered PDF pages or kept every
  spreadsheet row; it now checks the outcome the task asks for. Runs are
  re-graded with `--regrade`.

## Run

```bash
uv run python evals/skill/run.py --check                    # graders vs expert/naive solutions
uv run python evals/skill/run.py --reps 3 --parallel 6      # every task, both arms
uv run python evals/skill/run.py --tasks scans --reps 1 --model openai-codex/gpt-6-luna
uv run python evals/skill/run.py --regrade evals/skill/runs/<stamp>
```

Results go to `evals/skill/runs/<stamp>/` (ignored by git): `report.md`, and
per run `result.json` and the agent's `session.jsonl`. Workspaces stay in
`~/.cache/attachments-skill-eval/<stamp>/`. The agent runs through Pi's
ChatGPT login (`openai-codex/...`); no API key is needed, and the tasks
never call a model API.
