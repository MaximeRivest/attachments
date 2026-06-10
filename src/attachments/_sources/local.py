"""Local filesystem sources: single files and directory walks.

Handles recursive directory walks — deterministic (sorted) order, with
VCS/cache directories pruned — expanding nested raw archives by
extension via ``archives.py``. Single local files are read in the
``unpack()`` dispatch itself (see ``__init__.py``).

Contributor note: to add a new source, add one module in this package,
register it at import time (plus an import line in the block at the
BOTTOM of ``__init__.py`` — top-of-file imports run before the registry
exists and circular-import), and add tests — see DEVELOPMENT.md
("Building New Sources").
"""

from __future__ import annotations

import os
from pathlib import Path

from .archives import _explode_archive_bytes, _is_raw_archive_name


def _walk_directory(path: Path) -> list[tuple[str, bytes]]:
    """Return ``(relative_path, bytes)`` for all files in a directory.

    Skips common VCS/cache directories like ``.git/`` by default.

    The walk is deterministic: directories and filenames are visited in
    sorted order, so artifact order — and therefore ``.text``, ``.chunk()``
    and the repr — never depends on filesystem internals or file-creation
    history (raw ``os.walk`` order varies across filesystems/machines,
    which would break prompt caching and reproducibility).
    """
    root = path.resolve()
    out: list[tuple[str, bytes]] = []
    for dirpath, dirnames, filenames in os.walk(root):
        # Skip common VCS and cache directories
        rel_dir = os.path.relpath(dirpath, root)
        if rel_dir == ".":
            rel_dir = ""
        # Prune directories we don't want to descend into
        for d in list(dirnames):
            if d in {".git", ".hg", ".svn", "__pycache__"}:
                dirnames.remove(d)
        # Sort in place so os.walk descends in deterministic order.
        dirnames.sort()

        for fn in sorted(filenames):
            fpath = Path(dirpath) / fn
            try:
                with open(fpath, "rb") as f:
                    data = f.read()
            except Exception:
                continue
            rel = os.path.join(rel_dir, fn) if rel_dir else fn
            # Expand nested archives in-place (by extension only)
            if _is_raw_archive_name(rel):
                out.extend(_explode_archive_bytes(rel, data))
            else:
                out.append((rel, data))
    return out
