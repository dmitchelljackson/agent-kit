"""Talking to the kit repo: install pages, report/take upstream changes, share back.

Projects own their copies. `.agent-kit.json` records the kit commit they were
last synced to; that is the only link. Divergence is normal and never
overwritten silently.
"""

from __future__ import annotations

import datetime as _dt
import io
import json
import re
import shutil
import subprocess
import tarfile
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from . import frontmatter as fm
from .config import AkitError, Project, cache_dir, kit_dir_override
from .wiki import EMBED_LINE_RE, LINK_RE, PAGE, Wiki

KIT_WIKI = "wiki"


# ---------------- git helpers ----------------

def git(*args: str, cwd: Path, check: bool = True) -> str:
    proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if check and proc.returncode:
        raise AkitError(f"git {' '.join(args)} failed in {cwd}:\n{proc.stderr.strip()}")
    return proc.stdout.strip()


def slug_of(url: str) -> str:
    m = re.search(r"github\.com[:/]([^/]+)/([^/.]+)", url)
    return f"{m.group(1)}__{m.group(2)}" if m else re.sub(r"[^A-Za-z0-9]+", "_", url)[-60:]


def owner_repo(url: str) -> str:
    m = re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?/?$", url)
    if not m:
        raise AkitError(f"Kit URL is not a GitHub repo: {url}")
    return f"{m.group(1)}/{m.group(2)}"


def existing_checkout(project: Project) -> Path | None:
    """The kit checkout if one is already on disk; never clones or fetches."""
    override = kit_dir_override()
    if override and (override / ".git").exists():
        return override
    d = cache_dir() / "kits" / slug_of(project.kit_url)
    return d if (d / ".git").exists() else None


def checkout(project: Project, fetch: bool = True) -> Path:
    """Local clone of the kit (AKIT_KIT_DIR / kit_dir override, else a cached clone)."""
    override = kit_dir_override()
    if override:
        if not (override / ".git").exists():
            raise AkitError(f"AKIT_KIT_DIR is not a git checkout: {override}")
        return override
    d = cache_dir() / "kits" / slug_of(project.kit_url)
    if not (d / ".git").exists():
        d.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", "--quiet", project.kit_url, str(d)], check=True)
    elif fetch:
        git("fetch", "--quiet", "origin", cwd=d)
    return d


def head(project: Project, repo: Path) -> str:
    for ref in (f"origin/{project.kit_ref}", "HEAD"):
        out = git("rev-parse", "--verify", "--quiet", ref, cwd=repo, check=False)
        if out:
            return out
    raise AkitError(f"Can't resolve kit ref {project.kit_ref} in {repo}")


def export(repo: Path, sha: str, dest: Path) -> Path:
    """Extract the kit's wiki at `sha` into dest; returns the wiki root."""
    data = subprocess.run(["git", "archive", "--format=tar", sha, KIT_WIKI], cwd=repo, capture_output=True)
    if data.returncode:
        raise AkitError(f"Can't read kit wiki at {sha[:10]}: {data.stderr.decode().strip()}")
    with tarfile.open(fileobj=io.BytesIO(data.stdout)) as tar:
        tar.extractall(dest, filter="data")
    return dest / KIT_WIKI


# ---------------- install ----------------

def _norm(text: str) -> str:
    return "\n".join(line.rstrip() for line in text.strip().split("\n"))


def install(project: Project, pages: list[str], recursive: bool) -> list[str]:
    repo = checkout(project)
    sha = project.commit or head(project, repo)
    log: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        kit = Wiki(export(repo, sha, Path(tmp)))
        local = Wiki(project.wiki)
        for page in pages:
            src = kit.root / page.strip("/")
            if not (src / PAGE).is_file():
                raise AkitError(f"Kit has no page '{page}' at {sha[:10]}. See `akit kit ls`.")
            # parents first, so the page lands inside an existing page tree
            rel_parts = Path(page.strip("/")).parts
            for i in range(1, len(rel_parts)):
                parent = Path(*rel_parts[:i])
                if not (local.root / parent / PAGE).exists():
                    _copy_page(kit, local, kit.root / parent, recursive=False, log=log)
            _copy_page(kit, local, src, recursive=recursive, log=log)
    if not project.commit:
        project.data["commit"] = sha
        project.save()
    return log


def _copy_page(kit: Wiki, local: Wiki, src: Path, recursive: bool, log: list[str]) -> None:
    rel = src.relative_to(kit.root)
    dst = local.root / rel
    dst.mkdir(parents=True, exist_ok=True)
    local_ids = local.by_id()
    renames: dict[str, str] = {}
    for f in sorted(src.iterdir()):
        if f.is_dir():
            if recursive and (f / PAGE).is_file():
                _copy_page(kit, local, f, recursive=True, log=log)
            continue
        target = dst / f.name
        if f.name == PAGE:
            continue  # written last, after renames are known
        if f.suffix == ".md":
            doc = fm.load(f)
            if doc.id and doc.id in local_ids:
                log.append(f"skip {rel / f.name} (atom already present at {local.rel(local_ids[doc.id][0])})")
                continue
            if (f.stem in local.by_name()) and doc.id:
                new = local.unique_name(f.stem)
                renames[f.stem] = new
                target = dst / f"{new}.md"
                log.append(f"rename {f.stem} -> {new} (name taken locally)")
        elif target.exists():
            log.append(f"skip {rel / f.name} (exists)")
            continue
        shutil.copy2(f, target)
        log.append(f"add {local.rel(target)}")
    page_dst = dst / PAGE
    if page_dst.exists():
        log.append(f"keep {local.rel(page_dst)} (already exists)")
        return
    text = (src / PAGE).read_text(encoding="utf-8")
    for old, new in renames.items():
        text = LINK_RE.sub(lambda m: m.group(0).replace(f"[[{old}", f"[[{new}", 1)
                           if m.group(2).strip().split("/")[-1] == old else m.group(0), text)
    page_dst.write_text(text, encoding="utf-8")
    log.append(f"add {local.rel(page_dst)}")


def available(project: Project) -> list[tuple[str, str, str, bool]]:
    repo = checkout(project)
    sha = head(project, repo)
    local = Wiki(project.wiki) if project.wiki.exists() else None
    with tempfile.TemporaryDirectory() as tmp:
        kit = Wiki(export(repo, sha, Path(tmp)))
        out = []
        for d in kit.page_dirs():
            rel = kit.rel(d)
            if rel == ".":
                continue
            doc = fm.load(d / PAGE)
            have = bool(local and (local.root / rel / PAGE).exists())
            out.append((rel, doc.title, doc.meta.get("summary", ""), have))
        return out


# ---------------- sync ----------------

@dataclass
class SyncReport:
    base: str
    head: str
    updated: list[tuple[str, str, str]] = field(default_factory=list)      # id, local path, kit path
    conflicts: list[tuple[str, str, str]] = field(default_factory=list)
    diverged: list[tuple[str, str]] = field(default_factory=list)          # id, local path
    removed: list[tuple[str, str]] = field(default_factory=list)
    new_atoms: list[tuple[str, str, str]] = field(default_factory=list)    # id, kit path, local page
    new_pages: list[tuple[str, str]] = field(default_factory=list)         # rel, title
    changed_pages: list[str] = field(default_factory=list)                 # _page.md changed upstream, unchanged locally

    @property
    def empty(self) -> bool:
        return not any([self.updated, self.conflicts, self.removed, self.new_atoms, self.new_pages, self.changed_pages])


def _atoms_by_id(w: Wiki) -> dict[str, fm.Doc]:
    return {d.id: d for d in w.atoms()}


def sync_report(project: Project) -> SyncReport:
    if not project.commit:
        raise AkitError("No kit commit recorded in .agent-kit.json; run `akit install` first.")
    repo = checkout(project)
    h = head(project, repo)
    rep = SyncReport(base=project.commit, head=h)
    if h == project.commit:
        return rep
    local = Wiki(project.wiki)
    with tempfile.TemporaryDirectory() as t1, tempfile.TemporaryDirectory() as t2:
        base_w, head_w = Wiki(export(repo, project.commit, Path(t1))), Wiki(export(repo, h, Path(t2)))
        base_a, head_a, local_a = _atoms_by_id(base_w), _atoms_by_id(head_w), _atoms_by_id(local)
        for i, ld in local_a.items():
            if i not in base_a:
                continue  # project-only atom
            b = base_a[i]
            if i not in head_a:
                rep.removed.append((i, local.rel(ld.path)))
                continue
            hd = head_a[i]
            lt, bt, ht = _norm(ld.path.read_text()), _norm(b.path.read_text()), _norm(hd.path.read_text())
            if bt == ht:
                if lt != bt:
                    rep.diverged.append((i, local.rel(ld.path)))
            elif lt == bt:
                rep.updated.append((i, local.rel(ld.path), head_w.rel(hd.path)))
            elif lt != ht:
                rep.conflicts.append((i, local.rel(ld.path), head_w.rel(hd.path)))
        for i, hd in head_a.items():
            if i in base_a or i in local_a:
                continue
            page_rel = head_w.rel(hd.path.parent)
            if (local.root / page_rel / PAGE).exists():
                rep.new_atoms.append((i, head_w.rel(hd.path), page_rel))
        for d in head_w.page_dirs():
            rel = head_w.rel(d)
            if rel == ".":
                continue
            lp, bp = local.root / rel / PAGE, base_w.root / rel / PAGE
            if not bp.exists() and not lp.exists() and (local.root / rel).parent.joinpath(PAGE).exists():
                rep.new_pages.append((rel, fm.load(d / PAGE).title))
            elif lp.exists() and bp.exists():
                lt, bt, ht = _norm(lp.read_text()), _norm(bp.read_text()), _norm((d / PAGE).read_text())
                if bt != ht and lt == bt:
                    rep.changed_pages.append(rel)
    return rep


def format_report(rep: SyncReport) -> str:
    lines = [f"Kit {rep.base[:10]} -> {rep.head[:10]}"]
    if rep.head == rep.base:
        return lines[0] + ": already up to date."

    def section(title: str, rows: list[str]) -> None:
        if rows:
            lines.append(f"\n{title} ({len(rows)}):")
            lines.extend(f"  {r}" for r in rows)

    section("Updated upstream, untouched here (safe to take)", [f"{i}  {p}" for i, p, _ in rep.updated])
    section("Page layouts updated upstream, untouched here (safe to take)", rep.changed_pages)
    section("New atoms on pages you have", [f"{i}  {k}" for i, k, _ in rep.new_atoms])
    section("Conflicts: changed both here and upstream (decide with the owner)", [f"{i}  {p}" for i, p, _ in rep.conflicts])
    section("Removed upstream (still here)", [f"{i}  {p}" for i, p in rep.removed])
    section("New pages available (install with `akit install <page>`)", [f"{r}  — {t}" for r, t in rep.new_pages])
    if rep.diverged:
        lines.append(f"\n{len(rep.diverged)} atom(s) differ locally from the kit (by choice); upstream hasn't changed them.")
    if rep.empty:
        lines.append("\nNothing upstream affects this project.")
    lines.append("\nTake changes: `akit sync --take <id|page> ...` or `--take-safe`. Then `akit sync --done` to record the new kit commit.")
    return "\n".join(lines)


def sync_take(project: Project, refs: list[str], take_safe: bool) -> list[str]:
    rep = sync_report(project)
    repo = checkout(project, fetch=False)
    local = Wiki(project.wiki)
    log: list[str] = []
    wanted = set(refs)
    if take_safe:
        wanted |= {i for i, _, _ in rep.updated} | {i for i, _, _ in rep.new_atoms} | set(rep.changed_pages)
    with tempfile.TemporaryDirectory() as tmp:
        head_w = Wiki(export(repo, rep.head, Path(tmp)))
        for i, lp, kp in rep.updated + rep.conflicts:
            if i in wanted:
                (local.root / lp).write_text((head_w.root / kp).read_text(encoding="utf-8"), encoding="utf-8")
                log.append(f"took {i} -> {lp}")
                wanted.discard(i)
        for rel in rep.changed_pages:
            if rel in wanted:
                shutil.copy2(head_w.root / rel / PAGE, local.root / rel / PAGE)
                log.append(f"took page layout {rel}")
                wanted.discard(rel)
        for i, kp, page_rel in rep.new_atoms:
            if i in wanted:
                src = head_w.root / kp
                name = local.unique_name(src.stem)
                shutil.copy2(src, local.root / page_rel / f"{name}.md")
                page = local.root / page_rel / PAGE
                if not _embeds(page, name):
                    with page.open("a", encoding="utf-8") as f:
                        f.write(f"\n![[{name}]]\n")
                log.append(f"added {i} -> {page_rel}/{name}.md")
                wanted.discard(i)
        for i, lp in rep.removed:
            if i in wanted:
                local.remove_atom(i)
                log.append(f"removed {i} ({lp})")
                wanted.discard(i)
    if wanted:
        raise AkitError("Not in the sync report: " + ", ".join(sorted(wanted)))
    return log


def _embeds(page: Path, name: str) -> bool:
    for line in page.read_text(encoding="utf-8").split("\n"):
        m = EMBED_LINE_RE.match(line)
        if m and m.group(1).strip().split("/")[-1] == name:
            return True
    return False


def sync_done(project: Project) -> str:
    repo = checkout(project, fetch=False)
    h = head(project, repo)
    project.data["commit"] = h
    project.save()
    return h


# ---------------- share ----------------

SECRET_PATTERNS = [
    ("private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b")),
    ("API key (sk-)", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}")),
    ("Slack token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("assigned secret", re.compile(r"(?i)\b(api[_-]?key|secret|token|passw(or)?d)\b\s*[:=]\s*['\"]?[A-Za-z0-9/+_\-]{16,}")),
]


def private_terms(project: Project) -> list[str]:
    terms = {project.name, project.root.name, *project.data.get("private_terms", [])}
    remote = git("remote", "get-url", "origin", cwd=project.root, check=False) if (project.root / ".git").exists() else ""
    m = re.search(r"[:/]([^/]+)/([^/]+?)(?:\.git)?$", remote or "")
    if m:
        terms.add(m.group(2))
    return sorted(t for t in terms if t and len(t) >= 3 and t.lower() not in {"app", "wiki", "project"})


def scan(project: Project, files: list[Path]) -> list[str]:
    findings = []
    terms = private_terms(project)
    for f in files:
        if not f.is_file():
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for n, line in enumerate(text.split("\n"), 1):
            for label, rx in SECRET_PATTERNS:
                if rx.search(line):
                    findings.append(f"{f.name}:{n}: possible {label}")
            for t in terms:
                if re.search(rf"(?i)\b{re.escape(t)}\b", line):
                    findings.append(f"{f.name}:{n}: project-specific term '{t}'")
    return findings


def collect(project: Project, targets: list[str], recursive: bool) -> list[tuple[Path, str]]:
    """Files to share, as (local path, wiki-relative destination)."""
    local = Wiki(project.wiki)
    out: dict[str, Path] = {}
    for t in targets:
        p = local.find(t)
        if p.name == PAGE:
            d = p.parent
            walker = d.rglob("*") if recursive else d.iterdir()
            for f in walker:
                if f.is_file() and not any(x.startswith(".") for x in f.relative_to(d).parts):
                    if recursive and f.parent != d and not (f.parent / PAGE).exists():
                        continue
                    out[local.rel(f)] = f
        else:
            out[local.rel(p)] = p
            page = p.parent / PAGE
            if page.exists():
                out.setdefault(local.rel(page), page)  # needed if the kit lacks this page
    return [(path, rel) for rel, path in sorted(out.items())]


def _share_state_dir() -> Path:
    d = cache_dir() / "shares"
    d.mkdir(parents=True, exist_ok=True)
    return d


def share_prepare(project: Project, targets: list[str], recursive: bool, approval: str,
                  findings_accepted: list[str]) -> dict:
    files = collect(project, targets, recursive)
    repo = checkout(project)
    base = head(project, repo)
    first = Path(files[0][1]).parent.name or "wiki"
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    branch = f"share/{re.sub(r'[^a-z0-9-]+', '-', first.lower()).strip('-')}-{stamp}"
    work = _share_state_dir() / branch.replace("/", "__")
    if work.exists():
        git("worktree", "remove", "--force", str(work), cwd=repo, check=False)
        shutil.rmtree(work, ignore_errors=True)
    git("worktree", "add", "--quiet", "-B", branch, str(work), base, cwd=repo)
    kit = Wiki(work / KIT_WIKI)
    kit_ids = kit.by_id()
    changes, renames = [], {}
    for path, rel in files:
        dest = kit.root / rel
        doc = fm.load(path) if path.suffix == ".md" else None
        if doc and doc.id and doc.id in kit_ids:
            dest = kit_ids[doc.id][0]
            kind = "change"
        elif doc and doc.id:
            if path.stem in kit.by_name():
                new = kit.unique_name(path.stem)
                renames[path.stem] = new
                dest = dest.with_name(f"{new}.md")
            kind = "new"
        elif path.name == PAGE and dest.exists():
            kind = "page-merge"
        else:
            kind = "new-file"
        dest.parent.mkdir(parents=True, exist_ok=True)
        if kind == "page-merge":
            _merge_page(dest, path)
        else:
            shutil.copy2(path, dest)
        changes.append({"kind": kind, "id": doc.id if doc else "", "title": doc.title if doc else "",
                        "path": (dest.relative_to(work)).as_posix()})
    for old, new in renames.items():
        for md in kit.root.rglob("*.md"):
            text = md.read_text(encoding="utf-8")
            new_text = LINK_RE.sub(lambda m: f"{m.group(1)}[[{new}{m.group(3)}{m.group(4)}]]"
                                   if m.group(2).strip() == old else m.group(0), text)
            if new_text != text:
                md.write_text(new_text, encoding="utf-8")
    kit.write_index()
    problems = [str(p) for p in kit.check() if p.level == "error"]
    body_path = _share_state_dir() / (branch.replace("/", "__") + ".md")
    body_path.write_text(_pr_body(project, work, changes, approval, findings_accepted, problems), encoding="utf-8")
    state = {"branch": branch, "worktree": str(work), "repo": str(repo), "body": str(body_path),
             "base": base, "changes": changes, "kit_url": project.kit_url}
    (_share_state_dir() / "latest.json").write_text(json.dumps(state, indent=2), encoding="utf-8")
    return state | {"problems": problems}


def _merge_page(dest: Path, src: Path) -> None:
    """Kit already has this page: append embeds the kit page doesn't have yet."""
    have = {m.group(1).strip().split("/")[-1] for line in dest.read_text(encoding="utf-8").split("\n")
            if (m := EMBED_LINE_RE.match(line))}
    add = [line for line in fm.load(src).body.split("\n")
           if (m := EMBED_LINE_RE.match(line)) and m.group(1).strip().split("/")[-1] not in have]
    if add:
        with dest.open("a", encoding="utf-8") as f:
            f.write("\n" + "\n".join(add) + "\n")


def _pr_body(project: Project, work: Path, changes: list[dict], approval: str, findings: list[str],
             problems: list[str]) -> str:
    template = (work / ".github" / "pull_request_template.md")
    body = template.read_text(encoding="utf-8") if template.exists() else "## Summary\nTODO(akit)\n"
    rows = "\n".join(f"- `{c['kind']}` {c['title'] or c['path']} — `{c['id'] or c['path']}`" for c in changes)
    kinds = {c["kind"] for c in changes}
    typ = "new" if kinds <= {"new", "new-file", "page-merge"} else "change"
    fills = {
        "{{TYPE}}": typ,
        "{{CHANGES}}": rows,
        "{{APPROVAL}}": ("Owner-approved in session (judge skipped)" if approval == "owner" else f"Share judge — {approval}"),
        "{{CHECKS}}": ("- Kit wiki check: " + ("pass" if not problems else "FAIL\n  - " + "\n  - ".join(problems))
                        + "\n- Secret/project-term scan: " + ("pass" if not findings else "findings accepted by owner:\n  - " + "\n  - ".join(findings))),
        "{{ORIGIN}}": f"- Kit version in source project: `{(project.commit or 'unknown')[:12]}`",
    }
    for k, v in fills.items():
        body = body.replace(k, v)
    return body


def share_submit(title: str, draft: bool) -> str:
    path = _share_state_dir() / "latest.json"
    if not path.exists():
        raise AkitError("Nothing prepared. Run `akit share <targets>` first.")
    st = json.loads(path.read_text(encoding="utf-8"))
    body = Path(st["body"]).read_text(encoding="utf-8")
    if "TODO(akit)" in body:
        raise AkitError(f"Fill in every TODO(akit) in {st['body']} before submitting.")
    work, repo = Path(st["worktree"]), Path(st["repo"])
    git("add", "-A", cwd=work)
    if not git("status", "--porcelain", cwd=work):
        raise AkitError("No changes to share (the kit already has this content).")
    git("commit", "--quiet", "-m", title, cwd=work)
    slug = owner_repo(st["kit_url"])
    can_push = subprocess.run(["gh", "api", f"repos/{slug}", "--jq", ".permissions.push"],
                              capture_output=True, text=True).stdout.strip() == "true"
    if can_push:
        git("push", "--quiet", "-u", "origin", st["branch"], cwd=work)
        head_ref = st["branch"]
    else:
        login = subprocess.run(["gh", "api", "user", "--jq", ".login"], capture_output=True, text=True, check=True).stdout.strip()
        subprocess.run(["gh", "repo", "fork", slug, "--clone=false"], capture_output=True, text=True)
        fork_url = f"https://github.com/{login}/{slug.split('/')[1]}.git"
        if "fork" not in git("remote", cwd=repo).split():
            git("remote", "add", "fork", fork_url, cwd=repo)
        git("push", "--quiet", "-u", "fork", st["branch"], cwd=work)
        head_ref = f"{login}:{st['branch']}"
    args = ["gh", "pr", "create", "--repo", slug, "--base", "main", "--head", head_ref,
            "--title", title, "--body-file", st["body"]]
    if draft:
        args.append("--draft")
    proc = subprocess.run(args, capture_output=True, text=True)
    if proc.returncode:
        raise AkitError(f"gh pr create failed:\n{proc.stderr.strip()}")
    git("worktree", "remove", "--force", str(work), cwd=repo, check=False)
    path.unlink()
    return proc.stdout.strip()
