"""Inputs of the reading cases (contract/reading.md), used by make.py.

Fixtures are folders written as ``{path: content}``: a string is UTF-8
text, ``{"b64": …}`` bytes, ``{"link": target}`` a symbolic link,
``{"dir": true}`` an empty folder. Each implementation writes the
fixture into a fresh temporary folder, makes it the current folder, and
runs ``att(input, options)`` with ``prefer: local-only`` and no service.
"""

# Literal file contents (SVG, CSV, notebooks) read best on one line each.
# ruff: noqa: E501

from __future__ import annotations

import base64
import bz2
import gzip
import io
import lzma
import struct
import tarfile
import zipfile


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


KEY = (
    "-----BEGIN OPENSSH PRIVATE KEY-----\n"
    "b3BlbnNzaC1rZXktdjEAAAAA\n"
    "-----END OPENSSH PRIVATE KEY-----\n"
)
CACHEDIR = "Signature: 8a477f597d28d172789f06886806bc55\n# a cache\n"
COMMIT = "0123456789abcdef0123456789abcdef01234567"


def zip_bytes(
    members: list[tuple[str, bytes]], *, flag_utf8: bool | None = None
) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in members:
            info = zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
            info.compress_type = (
                zipfile.ZIP_STORED
                if name.endswith("stored.txt")
                else zipfile.ZIP_DEFLATED
            )
            zf.writestr(info, data)
    return buf.getvalue()


def cp437_zip() -> bytes:
    """A zip whose member name is code page 437 (no UTF-8 flag): 0x82 is é."""
    data = zip_bytes([("caf_.txt", b"latte")])
    # The name appears in the local header and the central directory.
    return data.replace(b"caf_.txt", b"caf\x82.txt")


def tar_bytes(
    members: list[tuple[str, bytes]], *, mode: str = "w", extra=None
) -> bytes:
    if mode == "w:gz":  # gzip's header holds a time: fixed, so the cases are stable
        return gzip.compress(tar_bytes(members, extra=extra), mtime=0)
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode=mode, format=tarfile.PAX_FORMAT) as tf:
        for name, data in members:
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mtime = 1577836800
            tf.addfile(info, io.BytesIO(data))
        for info in extra or []:
            tf.addfile(info)
    return buf.getvalue()


def gnu_tar(members: list[tuple[str, bytes]]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.GNU_FORMAT) as tf:
        for name, data in members:
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mtime = 1577836800
            tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def symlink_info(name: str, target: str) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name)
    info.type = tarfile.SYMTYPE
    info.linkname = target
    return info


def dir_info(name: str) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name)
    info.type = tarfile.DIRTYPE
    return info


INNER_ZIP = zip_bytes([("inner/deep.txt", b"deep inside")])
ARCHIVE = zip_bytes(
    [
        ("README.md", b"# In the zip\n"),
        ("src/main.py", b"print(1)\n"),
        ("node_modules/pkg/index.js", b"x"),
        ("nested.zip", INNER_ZIP),
        ("stored.txt", b"kept as is"),
    ]
)

PROJECT = {
    "proj/.git/HEAD": "ref: refs/heads/main\n",
    "proj/.git/refs/heads/main": COMMIT + "\n",
    "proj/.git/config": (
        '[core]\n\tbare = false\n[remote "origin"]\n'
        "\turl = https://bot:ghp_tok@github.com/o/proj.git\n"
    ),
    "proj/.git/info/exclude": "excluded.txt\n",
    "proj/.gitignore": "*.log\nbuild/\n!keep.log\n/rootonly.txt\n",
    "proj/README.md": "# Proj\n\nA small project.\n",
    "proj/excluded.txt": "excluded by .git/info/exclude",
    "proj/rootonly.txt": "anchored pattern",
    "proj/debug.log": "noise",
    "proj/keep.log": "kept by a negated pattern",
    "proj/build/out.txt": "built",
    "proj/src/app.py": "print('hi')\n",
    "proj/src/rootonly.txt": "not anchored here",
    "proj/src/trace.log": "skipped by the parent's .gitignore",
    "proj/src/.env": "SECRET=1\n",
    "proj/src/util/helpers.py": "def helper():\n    return 1\n",
    "proj/.env.example": "SECRET=\n",
    "proj/.hidden/notes.txt": "hidden notes",
    "proj/.attachmentsignore": "docs/private/\n",
    "proj/docs/guide.md": "# Guide\n",
    "proj/docs/private/plan.md": "private",
    "proj/docs/sub/.gitignore": "*.tmp\n!wanted.tmp\n",
    "proj/docs/sub/x.tmp": "temporary",
    "proj/docs/sub/wanted.tmp": "wanted",
    "proj/docs/sub/y.md": "y",
    "proj/node_modules/x/index.js": "module.exports = 1\n",
    "proj/package-lock.json": "{}",
    "proj/lib.min.js": "minified",
    "proj/venv/pyvenv.cfg": "home = /usr\n",
    "proj/venv/lib/site.py": "venv code",
    "proj/cache/CACHEDIR.TAG": CACHEDIR,
    "proj/cache/blob.txt": "cached",
    "proj/deploy_key": KEY,
    "proj/server.pem": "pem",
    "proj/data/é.txt": "e acute",
    "proj/data/😀.txt": "emoji",
    "proj/data/ﬀ.txt": "ligature",
    "proj/data/Z.txt": "capital",
    "proj/data/a.txt": "lower",
    "proj/data/latin.txt": {"b64": b64(b"caf\xe9 cr\xe8me")},
    "proj/data/bom.txt": {"b64": b64("\ufeffwith a byte order mark".encode())},
    "proj/data/empty.txt": "",
    "proj/data/blob.bin": {"b64": b64(bytes(range(256)) * 2)},
    "proj/data/noext": "text without an extension",
    "proj/archive.zip": {"b64": b64(ARCHIVE)},
    "proj/link_in.md": {"link": "README.md"},
    "proj/link_dir": {"link": "src"},
    "proj/link_out.txt": {"link": "../outside.txt"},
    "outside.txt": "outside the project",
    "loose/a.md": "# A\n",
    "loose/b/c.txt": "c",
    "loose/b/d.txt": "d",
    "loose/b/e/f.txt": "f",
    "loose/big.txt": "x" * 3000,
}


def trees_cases() -> list[dict]:
    calls: list[tuple[str, str, dict]] = [
        ("a folder", "proj", {}),
        ("a folder written with a slash", "proj/", {}),
        ("hidden files", "proj", {"hidden": True}),
        ("ignore: none", "proj", {"ignore": "none"}),
        (
            "ignore patterns and a negation",
            "proj",
            {"ignore": "*.md, !debug.log, data/"},
        ),
        (
            "ignore: none plus a pattern",
            "proj",
            {"ignore": "none, node_modules/, .git/"},
        ),
        ("ignore: minimal warns", "loose", {"ignore": "minimal"}),
        (
            "ignore words that change nothing",
            "loose",
            {"ignore": "standard, gitignore"},
        ),
        (
            "a negated secret",
            "proj",
            {"ignore": "!deploy_key, !.env, !server.pem", "hidden": True},
        ),
        ("glob", "proj", {"glob": "*.py"}),
        (
            "glob with an alias and two patterns",
            "proj",
            {"include": "*.md, data/*.txt"},
        ),
        ("not recursive", "proj", {"recursive": False}),
        ("max_files", "proj", {"max_files": 3}),
        ("max_files 0 is no limit", "loose", {"max_files": 0}),
        ("max_size skips what does not fit", "loose", {"max_size": 10}),
        ("max_size as text", "loose", {"max_size": "3KB"}),
        ("max_size in KiB", "loose", {"max_size": "3 KiB"}),
        ("an invalid max_size", "loose", {"max_size": "lots"}),
        ("a negative max_files", "loose", {"max_files": -1}),
        ("files: false", "proj", {"files": False}),
        ("tree: false", "proj", {"tree": False}),
        ("tree: false, limit hit", "loose", {"tree": False, "max_files": 1}),
        ("tree: always", "loose", {"tree": "always"}),
        ("a subfolder of a repository", "proj/src", {}),
        ("a subfolder two levels down", "proj/docs/sub", {}),
        ("a folder outside any repository", "loose", {}),
        ("options in the string", "loose[max_files: 2, tree: false]", {}),
        ("a pattern", "proj/**/*.py", {}),
        ("a pattern one level", "proj/*.md", {}),
        ("a pattern in a subfolder", "proj/src/*.py", {}),
        ("a pattern through a wildcard folder", "proj/*/*.md", {}),
        ("a pattern with a class", "proj/data/[aZ].txt", {}),
        ("a pattern with a negated class", "proj/data/[!aZ].txt", {}),
        ("a pattern and hidden files", "proj/**/*.txt", {"hidden": True}),
        ("a pattern that names a hidden folder", "proj/.hidden/*.txt", {}),
        ("a pattern with tree: true", "loose/**/*.txt", {"tree": True}),
        ("a pattern with no match", "proj/*.nothing", {}),
        ("a pattern whose matches are all skipped", "proj/*.log", {}),
        (
            "a pattern whose matches are skipped, ignore: none",
            "proj/*.log",
            {"ignore": "none"},
        ),
        ("a file", "proj/README.md", {}),
        ("a file the rules would skip, named", "proj/debug.log", {}),
        ("a secret, named", "proj/src/.env", {}),
        (
            "a file with folder options",
            "proj/README.md",
            {"max_files": 3, "hidden": True},
        ),
        (
            "a file with folder options in the string",
            "proj/README.md[max_files: 3]",
            {},
        ),
        ("a latin-1 file", "proj/data/latin.txt", {}),
        ("a file with a byte order mark", "proj/data/bom.txt", {}),
        ("an empty file", "proj/data/empty.txt", {}),
        ("a binary file", "proj/data/blob.bin", {}),
        ("a file without an extension", "proj/data/noext", {}),
        ("a missing file", "proj/missing.txt", {}),
        ("a file named with brackets", "loose/a.md[]", {}),
        ("an archive", "proj/archive.zip", {}),
        ("an archive with its tree", "proj/archive.zip", {"tree": True}),
        ("an archive, files: false", "proj/archive.zip", {"files": False}),
        ("an archive, ignore: none", "proj/archive.zip", {"ignore": "none"}),
        ("an archive, max_files", "proj/archive.zip", {"max_files": 2}),
        ("an unknown option on a text file", "loose/a.md[pagez: 3]", {}),
        ("a list of inputs", ["loose/a.md", "proj/data/a.txt", "proj/missing.txt"], {}),
    ]
    return [
        {"name": name, "fixture": "PROJECT", "input": input, "options": options}
        for name, input, options in calls
    ]


# ---------------------------------------------------------------------------
# Archives given as bytes in hand
# ---------------------------------------------------------------------------


def archives_cases() -> list[dict]:
    texts = [("a.txt", b"alpha"), ("dir/b.md", b"# beta"), ("dir/sub/c.txt", b"gamma")]
    tar_with_odd = tar_bytes(
        [("x.txt", b"regular")],
        extra=[symlink_info("link.txt", "x.txt"), dir_info("folder")],
    )
    long_name = "a/" + "very-long-folder-name/" * 6 + "file.txt"
    samples: list[tuple[str, str, bytes, dict, list[str]]] = [
        ("a zip", "bundle.zip", zip_bytes(texts), {}, []),
        ("a zip, its tree", "bundle.zip", zip_bytes(texts), {"tree": True}, []),
        ("a zip, glob", "bundle.zip", zip_bytes(texts), {"glob": "dir/*"}, []),
        (
            "a zip in a zip",
            "outer.zip",
            zip_bytes([("x.txt", b"x"), ("in.zip", INNER_ZIP)]),
            {},
            [],
        ),
        (
            "a zip named .zip that holds a plain file named .zip",
            "o.zip",
            zip_bytes([("fake.zip", b"not a zip")]),
            {},
            [],
        ),
        (
            "names that try to leave",
            "evil.zip",
            zip_bytes(
                [
                    ("../../etc/passwd", b"root"),
                    ("/abs/x.txt", b"abs"),
                    ("a\\b\\c.txt", b"win"),
                    ("./d/./e.txt", b"dots"),
                ]
            ),
            {},
            [],
        ),
        (
            "folders are not members",
            "d.zip",
            zip_bytes([("folder/", b""), ("folder/f.txt", b"f")]),
            {},
            [],
        ),
        ("UTF-8 names", "u.zip", zip_bytes([("naïve/😀.txt", b"utf8")]), {}, []),
        ("code page 437 names", "c.zip", cp437_zip(), {}, []),
        ("an empty zip", "e.zip", zip_bytes([]), {}, []),
        ("an empty zip, its tree", "e.zip", zip_bytes([]), {"tree": True}, []),
        (
            "generated and secret members",
            "g.zip",
            zip_bytes(
                [
                    ("node_modules/m/i.js", b"m"),
                    (".env", b"S=1"),
                    ("k.txt", KEY.encode()),
                    ("venv/pyvenv.cfg", b"h"),
                    ("venv/x.py", b"v"),
                    ("ok.txt", b"ok"),
                    (".gitignore", b"*.tmp\n"),
                    ("t.tmp", b"t"),
                ]
            ),
            {},
            [],
        ),
        ("a tar", "b.tar", tar_bytes(texts), {}, []),
        ("a gzip tar", "b.tar.gz", tar_bytes(texts, mode="w:gz"), {}, []),
        ("a .tgz", "b.tgz", tar_bytes(texts, mode="w:gz"), {}, []),
        ("a tar with a link and a folder", "odd.tar", tar_with_odd, {}, []),
        (
            "a tar with a long name (pax)",
            "long.tar",
            tar_bytes([(long_name, b"long")]),
            {},
            [],
        ),
        (
            "a tar with a long name (GNU)",
            "gnu.tar",
            gnu_tar([(long_name, b"gnu long")]),
            {},
            [],
        ),
        (
            "a tar with a non-ASCII name",
            "n.tar",
            tar_bytes([("été/ñ.txt", b"pax utf8")]),
            {},
            [],
        ),
        (
            "a tar in a zip",
            "mix.zip",
            zip_bytes([("t.tar.gz", tar_bytes(texts, mode="w:gz"))]),
            {},
            [],
        ),
        ("bytes named .zip that are not an archive", "fake.zip", b"just text", {}, []),
        (
            "a bz2 tar",
            "b.tar.bz2",
            tar_bytes(texts, mode="w:bz2"),
            {},
            ["archive/bz2-xz"],
        ),
        ("a .tbz2", "b.tbz2", tar_bytes(texts, mode="w:bz2"), {}, ["archive/bz2-xz"]),
        (
            "an xz tar",
            "b.tar.xz",
            tar_bytes(texts, mode="w:xz"),
            {},
            ["archive/bz2-xz"],
        ),
        ("a .txz", "b.txz", tar_bytes(texts, mode="w:xz"), {}, ["archive/bz2-xz"]),
        (
            "a zip by content but not by name is not expanded",
            "lib.jar",
            zip_bytes([("word/document.xml", b"<w/>")]),
            {},
            [],
        ),
        ("a zip, max_files", "bundle.zip", zip_bytes(texts), {"max_files": 1}, []),
        ("a zip, files: false", "bundle.zip", zip_bytes(texts), {"files": False}, []),
    ]
    _ = (gzip, bz2, lzma, struct)  # the formats tarfile writes with
    return [
        {
            "name": name,
            "input": {"name": fname, "bytes_b64": b64(data)},
            "options": options,
            **({"requires": requires} if requires else {}),
        }
        for name, fname, data, options, requires in samples
    ]


# ---------------------------------------------------------------------------
# Inputs of every kind
# ---------------------------------------------------------------------------


def inputs_cases() -> list[dict]:
    return [
        {
            "name": "named bytes",
            "input": {"name": "notes.md", "bytes_b64": b64(b"# Notes")},
        },
        {
            "name": "named bytes are not parsed for options",
            "input": {"name": "notes.md[pages: 1]", "bytes_b64": b64(b"# Notes")},
        },
        {
            "name": "unnamed bytes are called file",
            "input": {"name": None, "bytes_b64": b64(b"plain words")},
        },
        {
            "name": "unnamed bytes found by their content",
            "input": {"name": None, "bytes_b64": b64(bytes(range(256)))},
        },
        {"name": "bare bytes are refused", "input": {"bare_bytes_b64": b64(b"x")}},
        {"name": "a number is refused", "input": {"number": 42}},
        {
            "name": "a list mixes kinds",
            "input": [
                {"name": "a.txt", "bytes_b64": b64(b"a")},
                {"number": 1},
                [{"name": "b.txt", "bytes_b64": b64(b"b")}],
            ],
        },
        {"name": "an empty list", "input": []},
        {
            "name": "options apply to named bytes",
            "input": {"name": "a.txt", "bytes_b64": b64(b"a")},
            "options": {"pagez": 1},
        },
    ]


# ---------------------------------------------------------------------------
# Skip rules and patterns, as functions
# ---------------------------------------------------------------------------


def ignore_cases() -> list[dict]:
    rules = [
        (
            ["*.log"],
            [("a/b/debug.log", False), ("debug.log", False), ("debug.logs", False)],
        ),
        (["/*.log"], [("a/debug.log", False), ("x.log", False)]),
        (
            ["doc/*.txt"],
            [("doc/x.txt", False), ("doc/sub/x.txt", False), ("a/doc/x.txt", False)],
        ),
        (["**/foo"], [("a/b/foo", False), ("foo", False)]),
        (["a/**/b"], [("a/b", False), ("a/x/y/b", False), ("ab", False)]),
        (["abc/**"], [("abc/x/y", False), ("abc", True)]),
        (["**"], [("x", False), ("a/b", True)]),
        (["file[0-9].txt"], [("file7.txt", False), ("filex.txt", False)]),
        (
            ["file[!0-9].txt"],
            [("file7.txt", False), ("filex.txt", False), ("file/.txt", False)],
        ),
        (["[]a].txt"], [("].txt", False), ("a.txt", False)]),
        (["[z-a].txt"], [("z.txt", False)]),
        (["\\#notes", "\\!bang"], [("#notes", False), ("!bang", False)]),
        (["# comment", "  ", "x"], [("x", False), ("# comment", False)]),
        (
            ["trailing   ", "escaped\\ "],
            [("trailing", False), ("escaped ", False), ("escaped", False)],
        ),
        (["build/"], [("build", True), ("build", False), ("a/build", True)]),
        (["*.tmp", "!keep.tmp"], [("x.tmp", False), ("keep.tmp", False)]),
        (["!keep.tmp", "*.tmp"], [("keep.tmp", False)]),
        (["a?c"], [("abc", False), ("a/c", False)]),
        (["ü*.txt"], [("über.txt", False), ("Über.txt", False)]),
        (["?.txt"], [("😀.txt", False), ("ab.txt", False)]),
        (["*.TXT"], [("a.txt", False)]),
        (["a/"], [("a", True), ("x/a", True)]),
        (["/"], [("a", False)]),
        (["!"], [("a", False)]),
        (["a**b"], [("axyb", False), ("ax/yb", False)]),
        (["foo/**/"], [("foo/a", True), ("foo/a", False)]),
        (["[a-c]*"], [("bob", False), ("dave", False)]),
        (["\\[x]"], [("[x]", False), ("x", False)]),
        (["[["], [("[[", False)]),
    ]
    cases = []
    for patterns, paths in rules:
        for path, is_dir in paths:
            cases.append(
                {
                    "name": f"{patterns!r} on {path!r}{'/' if is_dir else ''}",
                    "call": "decide",
                    "patterns": patterns,
                    "path": path,
                    "is_dir": is_dir,
                }
            )
    engine = [
        ({}, ".git", True),
        ({}, "a/.hg", True),
        ({}, "src/.env", False),
        ({}, ".env.example", False),
        ({}, ".env.local", False),
        ({}, "home/.aws/credentials", False),
        ({}, "deploy/id_ed25519", False),
        ({}, "client_secret_123.json", False),
        ({}, "x.tfstate", False),
        ({}, "node_modules", True),
        ({}, "node_modules", False),
        ({}, "pkg.egg-info", True),
        ({}, "a/__pycache__", True),
        ({}, "uv.lock", False),
        ({}, "a/b/x.min.js", False),
        ({}, "x.map", False),
        ({}, ".DS_Store", False),
        ({}, ".idea", True),
        ({}, ".editorconfig", False),
        ({}, "src/app.py", False),
        ({}, "build", True),
        ({"hidden": True}, ".idea", True),
        ({"hidden": True}, ".env", False),
        ({"extra": ["!uv.lock"]}, "uv.lock", False),
        ({"extra": ["*.py"]}, "a.py", False),
        ({"extra": ["!.git"]}, ".git", True),
        ({"defaults": False}, ".env", False),
        ({"defaults": False}, "node_modules", True),
        ({"defaults": False}, ".git", True),
        ({"defaults": False, "extra": ["*.md"]}, "x.md", False),
    ]
    for opts, path, is_dir in engine:
        cases.append(
            {
                "name": f"engine {opts} on {path!r}{'/' if is_dir else ''}",
                "call": "check",
                "engine": opts,
                "path": path,
                "is_dir": is_dir,
            }
        )
    keys = [
        b"-----BEGIN OPENSSH PRIVATE KEY-----\nx",
        b"\xef\xbb\xbf  \n-----BEGIN RSA PRIVATE KEY-----",
        b"-----BEGIN PGP PRIVATE KEY BLOCK-----",
        b"-----BEGIN ENCRYPTED PRIVATE KEY-----",
        b"PuTTY-User-Key-File-3: ssh-ed25519",
        b"-----BEGIN PUBLIC KEY-----",
        b"# docs: -----BEGIN RSA PRIVATE KEY-----",
        b" " * 300 + b"-----BEGIN RSA PRIVATE KEY-----",
        b"-----BEGIN private KEY-----",
        b"PuTTY-User-Key-File-x",
        b"\t\x0b\x0c\r-----BEGIN EC PRIVATE KEY-----",
    ]
    for data in keys:
        cases.append(
            {"name": f"key file {data[:40]!r}", "call": "key", "bytes_b64": b64(data)}
        )
    return cases


def globs_cases() -> list[dict]:
    cases = []
    for pattern in [
        "docs/*.txt",
        "src/**/x.py",
        "src/*/file.txt",
        "file[1].txt",
        "plain/file.txt",
        "odd[name",
        "a/b[/c",
        "*.py",
        "/abs/dir/**/*.md",
        "/*.py",
        "a?b",
        "dir/[!x]",
    ]:
        cases.append(
            {"name": f"split {pattern!r}", "call": "split", "pattern": pattern}
        )
    matches = [
        (["*", "x.py"], False, ["a/x.py", "a/b/x.py", ".h/x.py", "x.py"]),
        (["**", "*.md"], False, ["a.md", "a/b/c.md", ".h/c.md", "a/.c.md", "a/b"]),
        (["**", "*.md"], True, ["a.md", ".h/c.md", "a/.c.md"]),
        (["**"], False, ["a", "a/b", ".a"]),
        ([".h", "*"], False, [".h/a", ".h/.b"]),
        (["*.txt"], False, ["é.txt", "😀.txt", ".txt", "a.txt/b"]),
        (["?.txt"], False, ["😀.txt", "a.txt", "ab.txt"]),
        (["[ab]*"], False, ["apple", "cherry", "b"]),
        (["[!ab]*"], False, ["apple", "cherry", ".c"]),
        (["[^ab]*"], False, ["apple", "cherry"]),
        (["[a-"], False, ["[a-", "a"]),
        (["a**b"], False, ["ab", "axyb", "ax/yb"]),
        (["d", "**", "f"], False, ["d/f", "d/x/f", "d/.x/f"]),
    ]
    for components, hidden, paths in matches:
        for path in paths:
            cases.append(
                {
                    "name": f"{'/'.join(components)!r} hidden={hidden} on {path!r}",
                    "call": "match",
                    "components": components,
                    "hidden": hidden,
                    "path": path,
                }
            )
    for text in [
        "docs/*.txt",
        "file[1].txt",
        "plain.txt",
        "odd[name",
        "a/[x]/b",
        "[]",
        "x[/]y",
        "?",
    ]:
        cases.append(
            {"name": f"is a pattern: {text!r}", "call": "is_pattern", "text": text}
        )
    return cases


# ---------------------------------------------------------------------------
# Text, sniffing, mentions
# ---------------------------------------------------------------------------


def _ooxml(kind: str) -> bytes:
    return zip_bytes([("[Content_Types].xml", b"<Types/>"), (f"{kind}/x.xml", b"<x/>")])


def text_cases() -> list[dict]:
    samples = {
        "ascii": b"hello",
        "utf-8": "naïve 😀".encode(),
        "a byte order mark is kept": "\ufeffbom".encode(),
        "latin-1": b"caf\xe9",
        "cp1252 quotes read as latin-1": b"\x93quoted\x94",
        "invalid utf-8 in the middle": b"ok \xff\xfe then",
        "a lone surrogate encoded": b"\xed\xa0\x80x",
        "overlong encoding": b"\xc0\xaf",
        "empty": b"",
        "crlf": b"a\r\nb\r\n",
        "nul inside": b"a\x00b",
    }
    cases = [
        {"name": f"decode: {k}", "call": "text", "bytes_b64": b64(v)}
        for k, v in samples.items()
    ]
    sniffs = {
        "pdf": b"%PDF-1.7 ...",
        "png": b"\x89PNG\r\n\x1a\n...",
        "jpeg": b"\xff\xd8\xff\xe0\x00\x10JFIF",
        "gif87": b"GIF87a...",
        "gif89": b"GIF89a...",
        "webp": b"RIFF\x12\x00\x00\x00WEBPVP8 ",
        "bmp, size 0": b"BM" + b"\x00" * 24,
        "bmp, size matches": b"BM" + (30).to_bytes(4, "little") + b"\x00" * 24,
        "bmp, size wrong": b"BM" + (31).to_bytes(4, "little") + b"\x00" * 24,
        "bmp, too short": b"BM\x00\x00",
        "text starting BM": b"BMW is a car maker, not a bitmap",
        "docx": _ooxml("word"),
        "xlsx": _ooxml("xl"),
        "pptx": _ooxml("ppt"),
        "plain zip": zip_bytes([("hello.txt", b"x")]),
        "zip without types": zip_bytes([("word/x.xml", b"x")]),
        "broken zip": b"PK\x03\x04 nope",
        "html doctype": b"  \n\t<!DOCTYPE HTML><html></html>",
        "html with bom": b"\xef\xbb\xbf<html lang='en'>",
        "html upper": b"<HTML><body/></HTML>",
        "xml": b"<xml>not html</xml>",
        "empty": b"",
        "plain": b"plain text content",
        "all bytes": bytes(range(256)),
        "html after 300 spaces": b" " * 300 + b"<html>",
    }
    cases += [
        {"name": f"sniff: {k}", "call": "sniff", "bytes_b64": b64(v)}
        for k, v in sniffs.items()
    ]
    texty = {
        "empty": b"",
        "ascii": b"hello\n",
        "nul": b"hello\x00",
        "latin-1": b"caf\xe9",
        "4% control": b"a" * 96 + b"\x01" * 4,
        "5% control": b"a" * 95 + b"\x01" * 5,
        "escape and bell": b"\x1b[0m\x07",
        "all bytes": bytes(range(1, 256)),
        "del": b"\x7f" * 10,
    }
    cases += [
        {"name": f"looks like text: {k}", "call": "is_text", "bytes_b64": b64(v)}
        for k, v in texty.items()
    ]
    return cases


def mentions_cases() -> list[dict]:
    prompts = [
        "Read `notes/a b.txt`, data.csv and report.pdf[pages: 1-2]. "
        "Mail me@x.org, see https://x.org/p.pdf). It's fine.",
        "Compare \"my notes.txt\" with “curly.md” and ‘single.md’ and 'plain.md'.",
        "Node.js and e.g. are not files; neither is v1.2 or 3.14.",
        "Look at src/app.py, ./rel.py, ../up.py, ~/home.txt and /abs/x.py.",
        "A path in a sentence: docs/guide.md.",
        "https://example.com/a_(b).html, (https://x.org/y) and https://x.org/z?q=1&r=2.",
        "Two of the same: a.txt a.txt `a.txt`",
        "Options: report.pdf[pages: 1-2, images: true] and table.xlsx[sheet: 'S 1'].",
        "Ünïcode naïve_file.md and 文件.txt and файл.md",
        "Inside words: abc.def@ghi.com x/y.z.w __init__.py",
        'Backtick `folder/` and quotes "unclosed',
        "",
        "it's Bob's file.txt",
        "a.verylongextension b.tar.gz c.TXT",
        "`https://x.org/q.pdf[pages: 1]`",
    ]
    return [
        {"name": f"mentions {i}: {p[:40]!r}", "call": "find", "prompt": p}
        for i, p in enumerate(prompts)
    ]


# ---------------------------------------------------------------------------
# Routing, with fake processors and a scripted service
# ---------------------------------------------------------------------------

#: Options the fake processor key ``.fake`` declares (both drivers register them).
FAKE_OPTIONS = [
    {
        "name": "pages",
        "type": "pages",
        "aliases": ["page"],
        "param": None,
        "default": None,
        "help": "",
        "example": "pages: 1-4",
    },
    {
        "name": "password",
        "type": "str",
        "aliases": ["pw"],
        "param": None,
        "default": None,
        "help": "",
        "example": "",
    },
    {
        "name": "dpi",
        "type": "int",
        "aliases": [],
        "param": None,
        "default": None,
        "help": "",
        "example": "dpi: 150",
    },
]

#: Fake processors (on ``.fake``): what each returns.
#: ``text``: the bytes as text, kind ``text``, the ``password`` and ``dpi`` it got
#: in ``meta.extra``; ``missing``: a missing-dependency error; ``partial``: text
#: with ``meta.extra.missing_dependency = "image"`` and one warning;
#: ``parse-error``: that error; ``throw``: raises; ``missing-module``: raises
#: what the language raises for a module that is not installed.
BEHAVIORS = ["text", "missing", "partial", "parse-error", "throw", "missing-module"]


def _served(text: str = "from the service", **meta) -> dict:
    return {
        "status": 200,
        "json": {
            "text": text,
            "images": [],
            "audio": [],
            "video": [],
            "meta": {"source": "x.fake", "kind": "text", **meta},
        },
    }


SERVED_PICTURE = {
    "status": 200,
    "json": {
        "text": "with a picture",
        "images": [
            {
                "name": "p1.png",
                "mimetype": "image/png",
                "bytes_b64": "iVBORw==",
                "page": 1,
            }
        ],
        "audio": [],
        "video": [],
        "meta": {"source": "x.fake", "kind": "pdf"},
    },
}
FAIL_500 = {"status": 500, "json": {"error": "boom"}}


def routing_cases() -> list[dict]:
    text = b64(b"local words")
    binary = b64(bytes(range(256)))
    cases = []

    def case(
        name,
        *,
        behavior="text",
        file=("x.fake", text),
        prefer="local",
        service=None,
        api_key=None,
        options=None,
        input_name=None,
        v1=False,
    ):
        c = {
            "name": name,
            "behavior": behavior,
            "input": {"name": input_name or file[0], "bytes_b64": file[1]},
            "prefer": prefer,
            "options": options or {},
        }
        if service is not None:
            c["service"] = {"answers": service, "v1": v1}
        if api_key:
            c["api_key"] = api_key
        return c

    cases += [
        case("local, no service: read here"),
        case("local, no service: a missing reader is an error", behavior="missing"),
        case(
            "local: a missing reader goes to the service",
            behavior="missing",
            service=[_served()],
        ),
        case("local: what reads here is not sent", service=[_served()]),
        case(
            "local: a failed service call is the error",
            behavior="missing",
            service=[FAIL_500],
        ),
        case(
            "local: a part missing, the service fails, the text stays",
            behavior="partial",
            service=[FAIL_500],
        ),
        case(
            "local: a part missing, the service has it",
            behavior="partial",
            service=[SERVED_PICTURE],
        ),
        case(
            "local: a parse error is final", behavior="parse-error", service=[_served()]
        ),
        case(
            "local: a crash is final, nothing is sent",
            behavior="throw",
            service=[_served()],
        ),
        case(
            "local: a missing module goes to the service",
            behavior="missing-module",
            service=[_served()],
        ),
        case("local: a crash without a service", behavior="throw"),
        case(
            "local: no reader for these bytes, the service reads them",
            file=("blob.zzz", binary),
            service=[_served()],
        ),
        case("local: no reader, no service", file=("blob.zzz", binary)),
        case("service: the service first", prefer="service", service=[_served()]),
        case(
            "service: refused, read here",
            prefer="service",
            service=[{"status": 401, "json": {"error": "Unauthorized"}}],
        ),
        case(
            "service: refused, no reader here",
            prefer="service",
            file=("blob.zzz", binary),
            service=[FAIL_500],
        ),
        case("service: no service configured, read here", prefer="service"),
        case(
            "local-only: a missing reader stays missing",
            behavior="missing",
            prefer="local-only",
            service=[_served()],
        ),
        case(
            "local-only: no reader",
            file=("blob.zzz", binary),
            prefer="local-only",
            service=[_served()],
        ),
        case("service-only: no service configured", prefer="service-only"),
        case("service-only: the service", prefer="service-only", service=[_served()]),
        case(
            "service-only: quota",
            prefer="service-only",
            service=[{"status": 402, "json": {"error": "quota"}}],
        ),
        case(
            "service-only: too large",
            prefer="service-only",
            service=[{"status": 413, "json": {"error": "big"}}],
        ),
        case(
            "service-only: an answer that is not an artifact",
            prefer="service-only",
            service=[{"status": 200, "json": {"text": 5}}],
        ),
        case(
            "service-only: an answer that is not JSON",
            prefer="service-only",
            service=[{"status": 200, "body": "<html>oops</html>"}],
        ),
        case(
            "service-only: an error that is not JSON",
            prefer="service-only",
            service=[{"status": 503, "body": "busy"}],
        ),
        case(
            "service-only: pictures come back as bytes",
            prefer="service-only",
            service=[SERVED_PICTURE],
        ),
        case(
            "service-only: a key is sent",
            prefer="service-only",
            api_key="att_secret",
            service=[_served()],
        ),
        case(
            "service-only: an address ending in /v1",
            prefer="service-only",
            service=[_served()],
            v1=True,
        ),
        case(
            "service-only: an answer without a source gets the file's name",
            prefer="service-only",
            service=[
                {
                    "status": 200,
                    "json": {
                        "text": "t",
                        "images": [],
                        "audio": [],
                        "video": [],
                        "meta": {},
                    },
                }
            ],
        ),
        case(
            "service-only: options as given, text as written",
            prefer="service-only",
            service=[_served()],
            input_name="x.fake[pw: 007, pages: 1-4, dpi: 300, zz: 1.50]",
            options={"dpi": 150, "extra": "kept"},
        ),
        case(
            "service-only: folder and processor options are not sent",
            prefer="service-only",
            service=[_served()],
            options={"max_files": 3, "processor": "default"},
        ),
        case(
            "service-only: a file name with quotes and spaces",
            prefer="service-only",
            service=[_served()],
            file=('a "q" é\tb.fake', text),
        ),
        case(
            "local: options resolved here, text as written",
            input_name="x.fake[password: 007, dpi: 300]",
        ),
        case("local: an unknown option warns", input_name="x.fake[pagez: 2]"),
        case("local: an invalid value warns", input_name="x.fake[dpi: high]"),
        case("local: an unknown processor warns", options={"processor": "nope"}),
        case(
            "local: options win over the string",
            input_name="x.fake[dpi: 300]",
            options={"dpi": 72},
        ),
    ]
    # Named bytes: the case's name is the input's name (a "[...]" in it is
    # parsed only for text inputs; these cases give text when they have one).
    for c in cases:
        name = c["input"]["name"]
        if "[" in name:
            c["input"] = {
                "text": name,
                "file": name.split("[", 1)[0],
                "bytes_b64": c["input"]["bytes_b64"],
            }
    return cases


# ---------------------------------------------------------------------------
# Downloads, from a scripted web server
# ---------------------------------------------------------------------------


def downloads_cases() -> list[dict]:
    routes = {
        "/notes.txt": {
            "status": 200,
            "headers": {"Content-Type": "text/plain"},
            "body": "plain notes",
        },
        "/d": {
            "status": 200,
            "headers": {"Content-Disposition": 'attachment; filename="report.md"'},
            "body": "# from a disposition",
        },
        "/e": {
            "status": 200,
            "headers": {
                "Content-Disposition": (
                    "attachment; filename*=UTF-8''r%C3%A9sum%C3%A9.txt"
                )
            },
            "body": "résumé",
        },
        "/old": {"status": 301, "headers": {"Location": "/moved/new.txt"}},
        "/moved/new.txt": {
            "status": 200,
            "headers": {"Content-Type": "text/plain"},
            "body": "moved here",
        },
        "/loop": {"status": 302, "headers": {"Location": "/loop"}},
        "/missing.txt": {"status": 404, "body": "not found"},
        "/": {
            "status": 200,
            "headers": {"Content-Type": "text/plain"},
            "body": "the root",
        },
        "/data.json": {
            "status": 200,
            "headers": {"Content-Type": "application/json"},
            "body": '{"a": 1}',
        },
        "/bundle.zip": {
            "status": 200,
            "headers": {"Content-Type": "application/zip"},
            "body_b64": b64(zip_bytes([("a.txt", b"alpha"), ("b/c.md", b"# c")])),
        },
        "/caf%C3%A9.txt": {"status": 200, "body": "percent-encoded name"},
        "/odd": {
            "status": 200,
            "headers": {"Content-Type": "text/plain"},
            "body_b64": b64(bytes(range(256))),
        },
    }
    calls = [
        ("a text file", "/notes.txt", {}, False),
        ("a name from Content-Disposition", "/d", {}, False),
        ("a name from filename*", "/e", {}, False),
        ("a redirect", "/old", {}, False),
        ("too many redirects", "/loop", {}, False),
        ("not found", "/missing.txt", {}, False),
        ("the root", "/", {}, False),
        ("JSON", "/data.json", {}, False),
        ("a zip by name", "/bundle.zip", {}, False),
        ("a zip, its tree", "/bundle.zip", {"tree": True}, False),
        ("a percent-encoded name", "/caf%C3%A9.txt", {}, False),
        ("options on a download", "/notes.txt[pagez: 1]", {}, False),
        ("folder options on a single download", "/notes.txt", {"max_files": 2}, False),
        ("bytes with no reader", "/odd", {}, False),
        ("a private address, blocked", "/notes.txt", {}, True),
    ]
    return [
        {"name": name, "path": path, "options": options, "block_private": block}
        for name, path, options, block in calls
    ], routes


def naming_cases() -> list[dict]:
    cds = [
        None,
        "",
        'attachment; filename="report.pdf"',
        "attachment; filename=data.csv",
        "attachment; filename*=UTF-8''na%C3%AFve%20file.txt; filename=\"fallback.txt\"",
        'inline; FILENAME="Upper.TXT"',
        "attachment; filename='single.txt'",
        "attachment; filename*=utf-8''%E2%82%AC%20rates.csv",
        "attachment",
    ]
    cases = [
        {"name": f"disposition {cd!r}", "call": "disposition", "value": cd}
        for cd in cds
    ]
    types = [
        (
            "README.md",
            "text/html; charset=utf-8",
            "https://github.com/o/r/blob/main/README.md",
        ),
        ("1706.03762", "application/pdf", "u"),
        ("data.csv", "text/plain", "u"),
        ("photo.JPEG", "image/jpeg", "u"),
        ("index.php", "text/html", "u"),
        ("page.HTM", "text/html", "u"),
        ("x.png", "image/jpeg", "u"),
        ("noext", "image/png", "u"),
        ("a.svgz", "image/svg+xml", "u"),
        ("v1.2.3", "application/pdf", "u"),
        ("table.json", "text/csv", "u"),
        ("x.html", "application/xhtml+xml", "u"),
        ("report.pdf", "APPLICATION/PDF", "u"),
        ("x.txt", None, "u"),
        ("x.do", "text/html", "u"),
        ("x.verylong", "text/html", "u"),
    ]
    cases += [
        {
            "name": f"type {n!r} {t!r}",
            "call": "type",
            "filename": n,
            "content_type": t,
            "url": u,
        }
        for n, t, u in types
    ]
    for url in [
        "https://github.com/psf/requests/blob/main/README.md",
        "https://example.com/a/b/blob/c",
        "https://www.github.com/o/r/blob/v1/a/b.py",
        "https://github.com/o/r/tree/main/x",
    ]:
        cases.append({"name": f"raw {url}", "call": "raw", "url": url})
    for name in [
        "normal/path/file.txt",
        "../../../etc/passwd",
        "/absolute/path.txt",
        "windows\\path\\f.txt",
        "./current/./dir/file.txt",
        "",
        "..",
        "a//b",
    ]:
        cases.append({"name": f"sanitize {name!r}", "call": "sanitize", "value": name})
    return cases


# ---------------------------------------------------------------------------
# The processors every implementation has: CSV, notebooks, SVG
# ---------------------------------------------------------------------------


def _nb(cells, metadata=None, **extra) -> bytes:
    import json

    doc = {
        "cells": cells,
        "metadata": metadata or {},
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    doc.update(extra)
    return json.dumps(doc, ensure_ascii=False).encode()


PNG_1x1 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="


def processors_cases() -> list[dict]:
    csvs: list[tuple[str, str, bytes, dict]] = [
        ("comma", "a.csv", b"name,age\nAda,36\nAlan,41\n", {}),
        ("semicolon", "a.csv", b"name;age\nAda;36\nAlan;41\n", {}),
        ("tab", "a.csv", b"name\tage\nAda\t36\n", {}),
        ("pipe", "a.csv", b"name|age\nAda|36\nAlan|41\n", {}),
        ("one column, csv", "a.csv", b"one\ntwo\nthree\n", {}),
        ("one column, tsv", "a.tsv", b"one\ntwo\nthree\n", {}),
        (
            "quoted fields with commas",
            "a.csv",
            b'name,quote\nAda,"hello, world"\nAlan,"a ""b"" c"\n',
            {},
        ),
        ("quoted with semicolons", "a.csv", b'"a";"b";"c"\n"1";"2";"3"\n', {}),
        ("single quotes", "a.csv", b"'a','b'\n'1','2'\n", {}),
        ("a quote then a space", "a.csv", b'x, "a", "b"\ny, "c", "d"\n', {}),
        ("a line break in quotes", "a.csv", b'a,b\n"line\nbreak",2\n', {}),
        ("crlf", "a.csv", b"a,b\r\n1,2\r\n", {}),
        ("old mac line ends", "a.csv", b"a,b\r1,2\r", {}),
        ("text after a closing quote", "a.csv", b'a,b\n"x"y,2\n', {}),
        ("an unterminated quote", "a.csv", b'a,b\n"open,2\n3,4\n', {}),
        ("a quote inside a field", "a.csv", b'a,b\nx"y,2\n', {}),
        ("empty lines", "a.csv", b"\na,b\n\n1,2\n\n", {}),
        ("ragged rows", "a.csv", b"a,b,c\n1\n1,2,3,4\n", {}),
        ("pipes and line breaks in cells", "a.csv", b'a,b\n"x|y","p\r\nq"\n', {}),
        ("empty", "a.csv", b"", {}),
        ("only white space", "a.csv", b" \n\t\n", {}),
        ("a header only", "a.csv", b"a,b,c\n", {}),
        (
            "rows truncated",
            "a.csv",
            b"n\n" + b"".join(b"%d\n" % i for i in range(10)),
            {"rows": 3},
        ),
        ("rows: 0", "a.csv", b"a,b\n1,2\n", {"rows": 0}),
        (
            "default truncation",
            "a.csv",
            b"n,m\n" + b"".join(b"%d,x\n" % i for i in range(205)),
            {},
        ),
        (
            "delimiter: semicolon",
            "a.csv",
            b"a;b,c\n1;2,3\n",
            {"delimiter": "semicolon"},
        ),
        ("delimiter: a character", "a.csv", b"a;b,c\n1;2,3\n", {"delimiter": ";"}),
        (
            "delimiter: TAB in capitals",
            "a.csv",
            b"a\tb\n1\t2\n",
            {"delimiter": " TAB "},
        ),
        ("delimiter: first character", "a.csv", b"a#b\n1#2\n", {"delimiter": "#!"}),
        ("latin-1", "a.csv", b"nom,ville\nZo\xe9,Montr\xe9al\n", {}),
        (
            "a byte order mark stays in the first cell",
            "a.csv",
            "\ufeffa,b\n1,2\n".encode(),
            {},
        ),
        ("a NUL in a cell", "a.csv", b"a,b\nx\x00y,2\n", {}),
        ("unicode", "a.csv", "été,😀\nñ,文\n".encode(), {}),
        ("commas and semicolons, both regular", "a.csv", b"a,b;c\n1,2;3\n4,5;6\n", {}),
        ("pipes and semicolons, both regular", "a.csv", b"a|b;c\n1|2;3\n4|5;6\n", {}),
        (
            "mostly consistent",
            "a.csv",
            b"a,b,c\n" + b"1,2,3\n" * 9 + b"1,2\n" + b"1;2\n" * 2,
            {},
        ),
        (
            "more than ten lines, a delimiter found later",
            "a.csv",
            b"x\n" * 10 + b"a;b\n1;2\n" * 3,
            {},
        ),
        (
            "a sample longer than 8192 characters",
            "a.csv",
            b"a,b\n" + b"1,2\n" * 2100 + b"x;y;z\n",
            {"rows": 2},
        ),
        ("an unknown option", "a.csv", b"a,b\n1,2\n", {"sheet": "x"}),
        (
            "text sniffed with quotes and a newline delimiter",
            "a.csv",
            b'"a"\n"b"\n"c"\n',
            {},
        ),
    ]
    cases = [
        {"name": f"csv: {n}", "input": {"name": f, "bytes_b64": b64(d)}, "options": o}
        for n, f, d, o in csvs
    ]

    code = {
        "cell_type": "code",
        "source": ["import math\n", "print(math.pi)"],
        "metadata": {},
        "execution_count": 1,
        "outputs": [
            {"output_type": "stream", "name": "stdout", "text": ["\n3.14159\n", "\n"]},
            {
                "output_type": "execute_result",
                "data": {"text/plain": ["'done'"]},
                "metadata": {},
                "execution_count": 1,
            },
            {
                "output_type": "display_data",
                "data": {
                    "image/png": [PNG_1x1[:40] + "\n", PNG_1x1[40:]],
                    "text/plain": "<Figure>",
                },
                "metadata": {},
            },
            {
                "output_type": "display_data",
                "data": {"image/png": PNG_1x1},
                "metadata": {},
            },
            {
                "output_type": "error",
                "ename": "E",
                "evalue": "v",
                "traceback": ["Traceback", "E: v"],
            },
            {"output_type": "clear_output"},
            {"output_type": "stream", "text": "\n\n"},
            "not an object",
        ],
    }
    md = {
        "cell_type": "markdown",
        "source": "# Title 😀\n\nSome *text*.",
        "metadata": {},
    }
    raw = {"cell_type": "raw", "source": None, "metadata": {}}
    long_out = {
        "cell_type": "code",
        "source": "x",
        "outputs": [
            {"output_type": "stream", "text": ("y" * 1990) + "   \n\t" + "z" * 50}
        ],
    }
    notebooks: list[tuple[str, bytes, dict]] = [
        ("cells of every kind", _nb([md, code, raw]), {}),
        ("with outputs", _nb([md, code, raw]), {"outputs": True}),
        (
            "the language from language_info",
            _nb([code], {"language_info": {"name": "julia"}}),
            {},
        ),
        (
            "the language from kernelspec",
            _nb([code], {"kernelspec": {"language": "R"}}),
            {},
        ),
        (
            "an empty language falls through",
            _nb(
                [code], {"language_info": {"name": ""}, "kernelspec": {"language": "r"}}
            ),
            {},
        ),
        ("a long output is cut", _nb([long_out]), {"outputs": True}),
        ("no cells", _nb([]), {}),
        ("cells that are not objects", _nb([1, None, md]), {}),
        (
            "a source that is a number",
            _nb(
                [
                    {"cell_type": "code", "source": 42},
                    {"cell_type": "markdown", "source": [1, True, None, "x"]},
                ]
            ),
            {},
        ),
        ("an unknown cell type", _nb([{"cell_type": "heading", "source": "h"}]), {}),
        ("no nbformat", b'{"cells": []}', {}),
        (
            "NaN in the metadata",
            b'{"cells": [{"cell_type": "markdown", "source": "x"}], '
            b'"metadata": {"v": NaN, "w": -Infinity}, "nbformat": 4}',
            {},
        ),
        ("nbformat 3", b'{"worksheets": [], "nbformat": 3}', {}),
        ("not JSON", b"{not json", {}),
        ("a JSON list", b"[1, 2]", {}),
        ("no cells key", b'{"metadata": {}}', {}),
        ("cells not a list", b'{"cells": {}}', {}),
        ("a byte order mark", "\ufeff".encode() + _nb([md]), {}),
        (
            "invalid UTF-8 is replaced",
            b'{"cells": [{"cell_type": "markdown", "source": "caf\xe9"}]}',
            {},
        ),
        ("metadata that is a list", b'{"cells": [], "metadata": [1]}', {}),
        (
            "an image that does not decode",
            _nb(
                [
                    {
                        "cell_type": "code",
                        "source": "",
                        "outputs": [
                            {"output_type": "display_data", "data": {"image/png": "a"}}
                        ],
                    }
                ]
            ),
            {"outputs": True},
        ),
    ]
    cases += [
        {
            "name": f"ipynb: {n}",
            "input": {
                "name": "my.notebook.IPYNB" if "kind" in n else "nb.ipynb",
                "bytes_b64": b64(d),
            },
            "options": o,
        }
        for n, d, o in notebooks
    ]

    ns = 'xmlns="http://www.w3.org/2000/svg"'
    svgs: list[tuple[str, str, bytes]] = [
        (
            "text elements",
            "d.svg",
            f'<svg {ns} width="10" height="20" viewBox="0 0 10 20"><title> A title </title><desc>A\n description</desc>'
            '<g><text x="1">Hello <tspan>big</tspan> world</text><text><textPath>on a path</textPath></text></g>'
            "<text>  </text><rect/></svg>".encode(),
        ),
        (
            "text outside text elements is not read",
            "d.svg",
            f"<svg {ns}><g>ignored</g><text>kept</text></svg>".encode(),
        ),
        (
            "nested text is read once",
            "d.svg",
            b"<svg><text>a<text>b</text>c</text></svg>",
        ),
        (
            "a prefix",
            "d.svg",
            b'<s:svg xmlns:s="http://www.w3.org/2000/svg"><s:title>t</s:title></s:svg>',
        ),
        ("an unbound prefix", "d.svg", b"<svg><s:title>t</s:title></svg>"),
        (
            "no text",
            "d.svg",
            f'<svg {ns} viewBox="0 0 1 1"><rect/><circle/></svg>'.encode(),
        ),
        ("a comment joins text", "d.svg", b"<svg><text>a<!-- c -->b</text></svg>"),
        (
            "a processing instruction joins text",
            "d.svg",
            b"<svg><text>a<?pi x?>b</text></svg>",
        ),
        ("CDATA", "d.svg", b"<svg><text><![CDATA[a < b]]> &amp; c</text></svg>"),
        (
            "entities from the DTD",
            "d.svg",
            b'<!DOCTYPE svg [<!ENTITY who "the &amp; world"><!ENTITY hi "Hello &who;">]><svg><text>&hi;!</text></svg>',
        ),
        (
            "an external entity",
            "d.svg",
            b'<!DOCTYPE svg [<!ENTITY e SYSTEM "f.txt">]><svg><text>&e;</text></svg>',
        ),
        ("an undefined entity", "d.svg", b"<svg><text>&nope;</text></svg>"),
        (
            "character references",
            "d.svg",
            b"<svg><text>caf&#xe9; &#233; &lt;&gt;&apos;&quot; &#x1F600;</text></svg>",
        ),
        ("an invalid character reference", "d.svg", b"<svg><text>&#0;</text></svg>"),
        ("line breaks", "d.svg", b"<svg><text>a\r\nb\rc&#13;d</text></svg>"),
        (
            "attribute values",
            "d.svg",
            b'<svg width=" 1\n\t2 " height="a&#10;b" viewBox="0&#9;0"/>',
        ),
        (
            "a public DOCTYPE",
            "d.svg",
            b'<?xml version="1.0" standalone="no"?>\n<!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN" '
            b'"http://www.w3.org/Graphics/SVG/1.1/DTD/svg11.dtd">\n<svg><title>t</title></svg>',
        ),
        (
            "latin-1 declared",
            "d.svg",
            b'<?xml version="1.0" encoding="ISO-8859-1"?><svg><text>caf\xe9 \x93</text></svg>',
        ),
        (
            "windows-1252 declared",
            "d.svg",
            b'<?xml version="1.0" encoding="windows-1252"?><svg><text>\x93q\x94</text></svg>',
        ),
        (
            "an unknown encoding",
            "d.svg",
            b'<?xml version="1.0" encoding="nope-8"?><svg/>',
        ),
        ("invalid UTF-8", "d.svg", b"<svg><text>\xe9</text></svg>"),
        ("a byte order mark", "d.svg", b"\xef\xbb\xbf<svg><title>bom</title></svg>"),
        ("UTF-16", "d.svg", "<svg><title>sixteen é</title></svg>".encode("utf-16")),
        (
            "white space before the declaration",
            "d.svg",
            b'  <?xml version="1.0"?><svg/>',
        ),
        (
            "white space before the root",
            "d.svg",
            b"\n\n  <svg><title>t</title></svg>\n",
        ),
        ("junk after the root", "d.svg", b"<svg/><svg/>"),
        ("text after the root", "d.svg", b"<svg/>text"),
        ("a mismatched tag", "d.svg", b"<svg><text></svg></text>"),
        ("unclosed", "d.svg", b"<svg><text>"),
        ("a duplicate attribute", "d.svg", b'<svg a="1" a="2"/>'),
        ("a control character", "d.svg", b"<svg><text>a\x01b</text></svg>"),
        ("empty", "d.svg", b""),
        ("not XML", "d.svg", b"just text"),
        ("a comment with --", "d.svg", b"<svg><!-- a -- b --></svg>"),
        (
            "gzip by name",
            "d.svgz",
            gzip.compress(b"<svg><title>zipped</title></svg>", mtime=0),
        ),
        (
            "gzip by content",
            "d.svg",
            gzip.compress(b"<svg><title>zipped</title></svg>", mtime=0),
        ),
        ("svgz that is not gzip", "d.svgz", b"<svg/>"),
        (
            "prefixed attributes are not width",
            "d.svg",
            b'<svg xmlns:a="u" a:width="1" width="2" xml:space="preserve"/>',
        ),
        ("ampersand without a name", "d.svg", b"<svg><text>a & b</text></svg>"),
        ("a less-than in an attribute", "d.svg", b'<svg a="<"/>'),
        (
            "ATTLIST defaults",
            "d.svg",
            b'<!DOCTYPE svg [<!ATTLIST svg width CDATA "100">]><svg><title>t</title></svg>',
        ),
        (
            "an entity with markup",
            "d.svg",
            b'<!DOCTYPE svg [<!ENTITY t "<title>from an entity</title>">]><svg>&t;</svg>',
        ),
    ]
    # Found by the differential test (ts/tests/crosslang.test.ts).
    svgs += [
        ("a version with a colon", "d.svg", b'<?xml version="1.:0"?><svg/>'),
        ("a version with a space", "d.svg", b'<?xml version="1.0 "?><svg/>'),
        (
            "a declaration out of order",
            "d.svg",
            b'<?xml version="1.0" standalone="yes" encoding="utf-8"?><svg/>',
        ),
        ("a processing instruction needs a space", "d.svg", b'<?pi"x"?><svg/>'),
        (
            "a target starting with xml",
            "d.svg",
            b"<?xmlx a?><svg><title>t</title></svg>",
        ),
        ("a colon in a target", "d.svg", b"<?p:i a?><svg/>"),
        ("a name starting with a colon", "d.svg", b'<svg :width="1"/>'),
        ("a name ending with a colon", "d.svg", b"<svg:/>"),
        ("two colons", "d.svg", b'<a:b:c xmlns:a="u"/>'),
        (
            "a DOCTYPE name with a prefix",
            "d.svg",
            b"<!DOCTYPE a:b><svg><title>t</title></svg>",
        ),
        ("a DOCTYPE name starting with a colon", "d.svg", b"<!DOCTYPE :vg><svg/>"),
        ("]]> in text", "d.svg", b"<svg><text>a]]>b</text></svg>"),
        ("]] in text", "d.svg", b"<svg><text>a]]b</text></svg>"),
        (
            "an incomplete reference in an entity",
            "d.svg",
            b'<!DOCTYPE svg [<!ENTITY e "x &y">]><svg/>',
        ),
    ]
    cases += [
        {"name": f"svg: {n}", "input": {"name": f, "bytes_b64": b64(d)}, "options": {}}
        for n, f, d in svgs
    ]
    return cases
