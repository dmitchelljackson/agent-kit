"""Directory scope: where a wiki change belongs.

A `.akit-scope` file holds one word, `main` or `branch`, and applies to its
directory and everything below it; the nearest file wins. `main` means "true
regardless of branch" (tickets, rules, sources): `akit land` may push it to main.
`branch` means "true once this branch's work merges" (the feature being built):
it rides with the branch. There are no per-file exceptions; a file that needs a
different scope belongs in a different directory. Scope files themselves always
ride with the branch, so a directory can't quietly become main-pushable.
"""

from __future__ import annotations

from pathlib import Path

from .config import AkitError

SCOPE_FILE = ".akit-scope"
SCOPES = ("main", "branch")
DEFAULT = "branch"


def read_scope_file(path: Path) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            if line not in SCOPES:
                raise AkitError(f"{path}: scope must be 'main' or 'branch', not '{line}'")
            return line
    raise AkitError(f"{path}: empty scope file (write 'main' or 'branch')")


def effective(wiki_root: Path, path: Path) -> tuple[str, Path | None]:
    """(scope, the .akit-scope file that decided it, or None for the default)."""
    root = wiki_root.resolve()
    p = path.resolve()
    d = p if p.is_dir() else p.parent
    while not d.exists() and d != root and root in d.parents:
        d = d.parent  # deleted directories: look at the nearest surviving ancestor
    while True:
        f = d / SCOPE_FILE
        if f.is_file():
            return read_scope_file(f), f
        if d == root or root not in d.parents:
            return DEFAULT, None
        d = d.parent


def describe(wiki_root: Path, path: Path) -> str:
    scope, src = effective(wiki_root, path)
    where = src.relative_to(wiki_root.resolve().parent).as_posix() if src else "default"
    return f"{scope} (from {where})"


def write(dir_: Path, scope: str) -> Path:
    if scope not in SCOPES:
        raise AkitError(f"scope must be 'main' or 'branch', not '{scope}'")
    f = dir_ / SCOPE_FILE
    f.write_text(scope + "\n", encoding="utf-8")
    return f


def all_scope_files(wiki_root: Path) -> list[Path]:
    return sorted(p for p in wiki_root.rglob(SCOPE_FILE) if p.is_file())
