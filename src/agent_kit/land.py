"""`akit land`: get wiki changes onto main without touching code or your branch.

The commit is always built in a temporary worktree based on main's tip, so the
current checkout, its branch, and any code changes are never touched. What gets
landed depends on the owner's landing mode (.agent-kit-owner.json):

  open    every changed wiki file (scope files ignored)
  scoped  only files in main-scoped directories (.akit-scope)
  pr      like scoped, but into one rolling PR branch instead of main

Only this command pushes wiki changes to main on an agent's behalf. The owner's
own git commands are never checked.
"""

from __future__ import annotations

import datetime as _dt
import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from . import bookmarks
from .config import CONFIG_NAME, AkitError, Project
from .scope import DEFAULT, SCOPE_FILE, SCOPES
from .wiki import Wiki

ROLLING_BRANCH = "akit/wiki-updates"
SPECIAL = {"index.md", "log.md"}  # wiki-root files akit rebuilds/merges on the target side


def _git(args: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if check and proc.returncode:
        raise AkitError(f"git {' '.join(args)} failed:\n{(proc.stderr or proc.stdout).strip()}")
    return proc


def _out(args: list[str], cwd: Path) -> str:
    return _git(args, cwd).stdout.strip()


@dataclass
class Change:
    path: str          # repo-relative, posix
    deleted: bool
    scope: str = ""
    why: str = ""


@dataclass
class Plan:
    mode: str
    repo: Path
    wiki_rel: str
    land: list[Change] = field(default_factory=list)
    stay: list[Change] = field(default_factory=list)
    log_changed: bool = False
    staged: list[str] = field(default_factory=list)


def _status(repo: Path, wiki_rel: str) -> list[Change]:
    raw = _git(["status", "--porcelain=v1", "-z", "--untracked-files=all", "--", wiki_rel], repo).stdout  # no strip: leading spaces matter
    entries = [e for e in raw.split("\0") if e] if raw else []
    changes, i = [], 0
    while i < len(entries):
        e = entries[i]
        xy, path = e[:2], e[3:]
        if xy[0] in "RC":
            changes.append(Change(path, deleted=False))
            if xy[0] == "R":
                changes.append(Change(entries[i + 1], deleted=True))
            i += 2
            continue
        changes.append(Change(path, deleted="D" in xy))
        i += 1
    return changes


class TargetScopes:
    """Scope as main sees it. Changed or deleted scope files don't count until they merge;
    a new scope file counts only for a directory main doesn't have yet (and lands with it)."""

    def __init__(self, repo: Path, wiki_rel: str, ref: str | None):
        self.repo, self.wiki_rel, self.ref = repo, wiki_rel, ref

    def _on_target(self, rel: str) -> str | None:
        if not self.ref:
            return None
        proc = _git(["show", f"{self.ref}:{rel}"], self.repo, check=False)
        return proc.stdout if proc.returncode == 0 else None

    def _dir_on_target(self, rel_dir: str) -> bool:
        if not self.ref:
            return False
        return _git(["cat-file", "-e", f"{self.ref}:{rel_dir}"], self.repo, check=False).returncode == 0

    def new_dir_scope_file(self, rel: str) -> bool:
        return self._on_target(rel) is None and not self._dir_on_target(Path(rel).parent.as_posix())

    def effective(self, rel: str) -> tuple[str, str]:
        d = Path(rel).parent
        while True:
            f = (d / SCOPE_FILE).as_posix()
            text = self._on_target(f)
            source = "main's"
            if text is None and (self.repo / f).is_file() and self.new_dir_scope_file(f):
                text, source = (self.repo / f).read_text(encoding="utf-8"), "new directory's"
            if text is not None:
                word = next((w for w in (l.split("#")[0].strip() for l in text.splitlines()) if w), "")
                if word in SCOPES:
                    return word, f"{word} (from {source} {f})"
            if d.as_posix() == self.wiki_rel or d == d.parent or d.as_posix() in ("", "."):
                return DEFAULT, f"{DEFAULT} (default)"
            d = d.parent


def _target_ref(repo: Path, target: str) -> str | None:
    for ref in (f"origin/{target}", target):
        if _ref_exists(repo, ref):
            return ref
    return None


def plan(project: Project, paths: list[str]) -> Plan:
    repo = Path(_out(["rev-parse", "--show-toplevel"], project.root)).resolve()
    wiki_root = project.wiki.resolve()
    wiki_rel = wiki_root.relative_to(repo).as_posix()
    mode = project.landing_mode
    p = Plan(mode=mode, repo=repo, wiki_rel=wiki_rel)
    scopes = TargetScopes(repo, wiki_rel, _target_ref(repo, project.data.get("main_branch", "main")))
    all_changes = _status(repo, wiki_rel)
    wanted = None
    if paths:
        wanted = []
        for raw in paths:
            target = (Path.cwd() / raw).resolve()
            if not target.exists() and (project.root / raw).exists():
                target = (project.root / raw).resolve()
            rel = target.relative_to(repo).as_posix() if repo in target.parents or target == repo else raw
            hits = [c for c in all_changes if c.path == rel or c.path.startswith(rel.rstrip("/") + "/")]
            if not hits:
                raise AkitError(f"No wiki changes under {raw}.")
            wanted += hits
    for c in (wanted if wanted is not None else all_changes):
        name = Path(c.path).name
        in_root = Path(c.path).parent.as_posix() == wiki_rel
        if in_root and name in SPECIAL:
            p.log_changed |= name == "log.md"
            continue
        if name == SCOPE_FILE:
            if mode != "open" and not c.deleted and scopes.new_dir_scope_file(c.path):
                c.scope, c.why = scopes.effective(c.path)
                (p.land if c.scope == "main" else p.stay).append(c)
            else:
                c.scope, c.why = "branch", "scope file changes ride with the branch; they apply once merged"
                p.stay.append(c)
            continue
        if mode == "open":
            c.scope, c.why = "main", "landing: open"
            p.land.append(c)
            continue
        c.scope, c.why = scopes.effective(c.path)
        (p.land if c.scope == "main" else p.stay).append(c)
    if wanted is not None and p.stay and mode != "open":
        lines = "\n".join(f"  {c.path}: {c.why}" for c in p.stay)
        raise AkitError(f"These are branch-scoped, so they can't be landed:\n{lines}\n"
                        "Branch-scoped pages merge with the work they describe: commit them on your branch.\n"
                        "If one really belongs on main, move it into a directory that is main-scoped on main (`akit scope` shows scopes).")
    if wanted is None:
        p.log_changed = p.log_changed or any(
            c.path == f"{wiki_rel}/log.md" for c in all_changes)
    return p


def format_plan(p: Plan, target: str) -> str:
    out = [f"landing mode: {p.mode}   target: {target}"]
    out.append(f"\nWill land ({len(p.land)}):" if p.land else "\nNothing to land.")
    out += [f"  {'D' if c.deleted else 'M'} {c.path}   [{c.why}]" for c in p.land]
    if p.stay:
        out.append(f"\nStays with your branch ({len(p.stay)}):")
        out += [f"  {'D' if c.deleted else 'M'} {c.path}   [{c.why}]" for c in p.stay]
    if p.land:
        out.append("\nAlso: new log entries are appended on the target; index and bookmark skills are rebuilt there.")
    return "\n".join(out)


# ---------------- landing ----------------

def _has_remote(repo: Path) -> bool:
    return _git(["remote", "get-url", "origin"], repo, check=False).returncode == 0


def _ref_exists(repo: Path, ref: str) -> bool:
    return _git(["rev-parse", "--verify", "--quiet", ref], repo, check=False).returncode == 0


def _new_log_text(repo: Path, wiki_rel: str) -> str:
    work = repo / wiki_rel / "log.md"
    if not work.exists():
        return ""
    now = work.read_text(encoding="utf-8")
    head = _git(["show", f"HEAD:{wiki_rel}/log.md"], repo, check=False)
    before = head.stdout if head.returncode == 0 else ""
    if now.startswith(before):
        return now[len(before):]
    seen = set(before.splitlines())
    return "\n".join(line for line in now.splitlines() if line not in seen)


def _copy_landed(p: Plan, wt: Path) -> list[str]:
    stage = []
    for c in p.land:
        dst = wt / c.path
        if c.deleted:
            if dst.exists():
                dst.unlink()
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p.repo / c.path, dst)
        stage.append(c.path)
    return stage


def _apply_derived(p: Plan, project: Project, wt: Path, log_text: str) -> list[str]:
    """Append the log and rebuild index and bookmark skills in the worktree. Returns paths to stage."""
    stage: list[str] = []
    wt_wiki = wt / p.wiki_rel
    if not wt_wiki.is_dir():
        raise AkitError(f"The target has no {p.wiki_rel}/ yet. Commit your akit setup to main first.")
    today = _dt.date.today().isoformat()
    entry = f"\n## [{today}] land | {len(p.land)} file(s)\n"
    log = wt_wiki / "log.md"
    text = log.read_text(encoding="utf-8") if log.exists() else "# Log\n"
    if log_text.strip():
        text = text.rstrip("\n") + "\n\n" + log_text.strip("\n") + "\n"
    log.write_text(text.rstrip("\n") + "\n" + entry, encoding="utf-8")
    Wiki(wt_wiki).write_index()
    proj_rel = project.root.resolve().relative_to(p.repo)
    wt_proj = wt / proj_rel
    cfg = wt_proj / CONFIG_NAME
    data = json.loads(cfg.read_text(encoding="utf-8")) if cfg.exists() else project.data
    wt_project = Project(root=wt_proj, data=data)
    bookmarks.sync(wt_project, Wiki(wt_wiki))
    stage += [f"{p.wiki_rel}/log.md", f"{p.wiki_rel}/index.md"]
    stage += [(proj_rel / d.relative_to(wt_proj)).as_posix() for d in bookmarks.skill_dirs(wt_project) if d.exists()]
    return stage


def _commit_in_worktree(p: Plan, project: Project, base: str, message: str, log_text: str) -> tuple[Path, str | None]:
    wt = Path(tempfile.mkdtemp(prefix="akit-land-"))
    wt.rmdir()
    _git(["worktree", "add", "--quiet", "--detach", str(wt), base], p.repo)
    landed = _copy_landed(p, wt)
    _git(["add", "-A", "--", *landed], wt)
    if not _git(["diff", "--cached", "--quiet"], wt, check=False).returncode:
        return wt, None  # the target already has exactly these files
    derived = _apply_derived(p, project, wt, log_text)
    p.staged = landed + derived
    _git(["add", "-A", "--", *derived], wt)
    _git(["commit", "--quiet", "-m", message], wt)
    return wt, _out(["rev-parse", "HEAD"], wt)


def _remove(p: Plan, wt: Path) -> None:
    _git(["worktree", "remove", "--force", str(wt)], p.repo, check=False)
    shutil.rmtree(wt, ignore_errors=True)


def land(project: Project, paths: list[str], message: str | None) -> str:
    target = project.data.get("main_branch", "main")
    p = plan(project, paths)
    if not p.land:
        return format_plan(p, target)
    msg = message or ("wiki: land " + ", ".join(sorted({Path(c.path).parent.name or c.path for c in p.land}))[:60])
    msg += "\n\n" + "\n".join(f"{'D' if c.deleted else 'M'} {c.path}" for c in p.land) + "\n\nLanded by akit."
    log_text = _new_log_text(p.repo, p.wiki_rel)
    if p.mode == "pr":
        return _land_pr(p, project, msg, log_text, target, reason="landing mode: pr")

    remote = _has_remote(p.repo)
    current = _out(["rev-parse", "--abbrev-ref", "HEAD"], p.repo)
    if remote:
        _git(["fetch", "--quiet", "origin", target], p.repo)
    local_ahead = (remote and current == target and _ref_exists(p.repo, f"origin/{target}")
                   and int(_out(["rev-list", "--count", f"origin/{target}..{target}"], p.repo)) > 0)
    if not remote or local_ahead:
        # No remote, or unpushed work of yours on main: commit locally, never push your commits.
        base = target
        wt, sha = _commit_in_worktree(p, project, base, msg, log_text)
        try:
            if sha is None:
                return "Already on " + target + ": nothing new to land."
            _advance_local(p, current, target, sha, wt)
        finally:
            _remove(p, wt)
        why = "no remote" if not remote else f"your {target} has unpushed commits, and akit never pushes your commits"
        return format_plan(p, target) + f"\n\nCommitted {sha[:10]} on local {target} ({why}). Push when you're ready."

    for attempt in range(3):
        base = f"origin/{target}"
        wt, sha = _commit_in_worktree(p, project, base, msg, log_text)
        try:
            if sha is None:
                return f"Already on {target}: nothing new to land."
            push = _git(["push", "--quiet", "origin", f"HEAD:refs/heads/{target}"], wt, check=False)
            if push.returncode == 0:
                if current == target and _out(["rev-parse", target], p.repo) == _out(["rev-parse", f"{sha}^"], p.repo):
                    _advance_local(p, current, target, sha, wt)
                    note = f"Your {target} is updated to match."
                elif current == target:
                    note = f"Your local {target} is behind origin; pull when convenient."
                else:
                    note = (f"Your branch still has these files modified (identical to {target}); they merge cleanly. "
                            "Commit them with your branch or `git checkout -- <file>` them.")
                _git(["fetch", "--quiet", "origin", target], p.repo, check=False)
                return format_plan(p, target) + f"\n\nLanded {sha[:10]} on {target}. {note}"
            err = push.stderr
            if "protected" in err.lower() or "GH006" in err or "required" in err.lower():
                return _land_pr(p, project, msg, log_text, target, reason=f"{target} is protected")
            if "non-fast-forward" in err or "fetch first" in err or "rejected" in err:
                _git(["fetch", "--quiet", "origin", target], p.repo)
                continue
            raise AkitError(f"Push failed:\n{err.strip()}")
        finally:
            _remove(p, wt)
    raise AkitError(f"{target} kept moving; tried 3 times. Run `akit land` again.")


def _advance_local(p: Plan, current: str, target: str, sha: str, wt: Path) -> None:
    if current == target:
        # Fast-forward the checked-out branch, bring the log over (it gained a land entry),
        # then resync only the landed paths in the index. Nothing else is touched.
        _git(["update-ref", f"refs/heads/{target}", sha], p.repo)
        shutil.copy2(wt / p.wiki_rel / "log.md", p.repo / p.wiki_rel / "log.md")
        _git(["reset", "-q", "--", *p.staged], p.repo, check=False)
    else:
        _git(["update-ref", f"refs/heads/{target}", sha], p.repo)


def _land_pr(p: Plan, project: Project, msg: str, log_text: str, target: str, reason: str) -> str:
    if not _has_remote(p.repo):
        raise AkitError("Landing through a PR needs a GitHub remote named origin.")
    _git(["fetch", "--quiet", "origin"], p.repo)
    open_pr = subprocess.run(["gh", "pr", "list", "--head", ROLLING_BRANCH, "--state", "open", "--json", "url", "-q", ".[0].url"],
                             cwd=p.repo, capture_output=True, text=True)
    pr_url = open_pr.stdout.strip() if open_pr.returncode == 0 else ""
    base = f"origin/{ROLLING_BRANCH}" if pr_url and _ref_exists(p.repo, f"origin/{ROLLING_BRANCH}") else f"origin/{target}"
    wt, sha = _commit_in_worktree(p, project, base, msg, log_text)
    try:
        if sha is None:
            return f"Nothing new to land ({ROLLING_BRANCH} already has it)."
        _git(["push", "--quiet", "--force-with-lease", "origin", f"HEAD:refs/heads/{ROLLING_BRANCH}"], wt)
    finally:
        _remove(p, wt)
    if not pr_url:
        made = subprocess.run(["gh", "pr", "create", "--head", ROLLING_BRANCH, "--base", target,
                               "--title", "Wiki updates (akit)",
                               "--body", "Main-scoped wiki changes landed by `akit land`. Merge whenever; new landings add commits here."],
                              cwd=p.repo, capture_output=True, text=True)
        pr_url = made.stdout.strip() if made.returncode == 0 else f"(couldn't open a PR: {made.stderr.strip()}; branch {ROLLING_BRANCH} is pushed)"
    return format_plan(p, f"PR {ROLLING_BRANCH}") + f"\n\nLanded {sha[:10]} on {ROLLING_BRANCH} ({reason}): {pr_url}"
