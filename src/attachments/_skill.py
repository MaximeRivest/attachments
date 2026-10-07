"""The coding-agent skill shipped in the package: where it is, and installing it.

``att --skill`` reports where the skill is and whether each coding agent on
this machine has it (up to date or not); ``att --skill --install`` copies it
to every agent found (Claude Code, Pi, Codex), or to the skills folders
named after ``--install``.

The skill lives in ``attachments/skill/`` inside the installed package, so
the copy an agent gets always matches the code it describes.

Safety rules for installing:

* A folder that is a link (a developer's checkout) is reported and left
  alone: it stays current by itself.
* An existing folder is replaced only when it is this skill (its
  ``SKILL.md`` declares ``name: attachments``); anything else is left alone.
* The new copy is written beside the target and swapped in by renames, so
  an interrupted install never leaves a half-written skill behind.
"""

from __future__ import annotations

import filecmp
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

__all__ = ["SKILL_DIR", "SKILL_NAME", "AGENT_SKILLS", "status", "install"]

#: The skill folder inside the installed package.
SKILL_DIR = Path(__file__).resolve().parent / "skill"

#: Folder name of the skill in every agent's skills folder.
SKILL_NAME = "attachments"

#: Where coding agents look for skills. An agent counts as present when the
#: parent of its skills folder exists (its home folder, e.g. ``~/.claude``).
AGENT_SKILLS = {
    "Claude Code": "~/.claude/skills",
    "Pi": "~/.pi/agent/skills",
    "Codex": "~/.codex/skills",
}

_IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store")


@dataclass(frozen=True)
class Place:
    """One agent's copy: where it is and its state."""

    agent: str
    path: Path
    state: str  # "up to date" | "out of date" | "linked" | "not installed" | "other"


def _is_ours(folder: Path) -> bool:
    """True when *folder* holds this skill (``name: attachments`` in front matter)."""
    skill_md = folder / "SKILL.md"
    if not skill_md.is_file():
        return False
    head = skill_md.read_text(encoding="utf-8", errors="replace").split("---", 2)
    return len(head) == 3 and f"\nname: {SKILL_NAME}\n" in f"\n{head[1]}\n"


def _same_tree(a: Path, b: Path) -> bool:
    """True when folders *a* and *b* hold the same files with the same bytes."""
    cmp = filecmp.dircmp(a, b, ignore=["__pycache__", ".DS_Store"])
    if cmp.left_only or cmp.right_only or cmp.funny_files:
        return False
    _, mismatch, errors = filecmp.cmpfiles(a, b, cmp.common_files, shallow=False)
    if mismatch or errors:
        return False
    return all(_same_tree(a / d, b / d) for d in cmp.common_dirs)


def _state(here: Path) -> str:
    if here.is_symlink():
        return "linked"
    if not here.exists():
        return "not installed"
    if not _is_ours(here):
        return "other"
    return "up to date" if _same_tree(SKILL_DIR, here) else "out of date"


def _agent_folders() -> dict[str, Path]:
    """Skills folders of the agents present on this machine."""
    found: dict[str, Path] = {}
    for agent, folder in AGENT_SKILLS.items():
        path = Path(folder).expanduser()
        if path.parent.is_dir():
            found[agent] = path
    return found


def status() -> list[Place]:
    """The skill's state for every agent present on this machine."""
    return [
        Place(agent, folder / SKILL_NAME, _state(folder / SKILL_NAME))
        for agent, folder in _agent_folders().items()
    ]


def _copy_into(folder: Path) -> None:
    """Write the skill to ``folder/attachments``, swapping it in atomically."""
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / SKILL_NAME
    staging = Path(tempfile.mkdtemp(prefix=f".{SKILL_NAME}-new-", dir=folder))
    old = folder / f".{SKILL_NAME}-old"
    try:
        shutil.copytree(SKILL_DIR, staging / SKILL_NAME, ignore=_IGNORE)
        if old.exists():
            shutil.rmtree(old)
        if target.exists():
            target.rename(old)
        (staging / SKILL_NAME).rename(target)
    except BaseException:
        if old.exists() and not target.exists():
            old.rename(target)  # put the previous copy back
        raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)
        shutil.rmtree(old, ignore_errors=True)


def install(folders: list[Path] | None = None) -> list[tuple[Path, str]]:
    """Install or update the skill; return ``(path, outcome)`` per target.

    *folders* are skills folders (the skill goes in ``<folder>/attachments``);
    ``None`` means every agent present on this machine. Outcomes:
    ``"installed"``, ``"updated"``, ``"already up to date"``, ``"left alone:
    a link to …"`` or ``"left alone: holds something else"``.
    """
    targets = (
        list(_agent_folders().values())
        if folders is None
        else [Path(f).expanduser() for f in folders]
    )
    results: list[tuple[Path, str]] = []
    for folder in targets:
        here = folder / SKILL_NAME
        state = _state(here)
        if state == "linked":
            results.append((here, f"left alone: a link to {here.resolve()}"))
        elif state == "other":
            results.append((here, "left alone: holds something else"))
        elif state == "up to date":
            results.append((here, "already up to date"))
        else:
            _copy_into(folder)
            results.append((here, "updated" if state == "out of date" else "installed"))
    return results


def main(args: list[str]) -> int:
    """``att --skill [--install [DIR ...]]``; *args* follow ``--skill``."""
    from . import __version__

    if not args:
        print(f"attachments skill ({__version__}): {SKILL_DIR}")
        places = status()
        for place in places:
            print(f"  {place.agent:<12} {place.path}: {place.state}")
        if not places:
            print("  no coding agent found here (Claude Code, Pi, Codex)")
        print("install or update it: att --skill --install [SKILLS_DIR ...]")
        return 0
    if args[0] != "--install":
        print(
            f"att --skill: unexpected {args[0]!r}; "
            "usage: att --skill [--install [SKILLS_DIR ...]]",
            file=sys.stderr,
        )
        return 2
    folders = [Path(a) for a in args[1:]] or None
    if folders is None and not _agent_folders():
        print(
            "att --skill --install: no coding agent found here "
            "(Claude Code, Pi, Codex); name a skills folder: "
            "att --skill --install SKILLS_DIR",
            file=sys.stderr,
        )
        return 1
    failed = False
    for path, outcome in install(folders):
        if outcome in ("installed", "updated"):
            outcome = f"{outcome} (attachments {__version__})"
        refused = outcome == "left alone: holds something else"
        failed |= refused
        print(f"{path}: {outcome}", file=sys.stderr if refused else sys.stdout)
    return 1 if failed else 0
