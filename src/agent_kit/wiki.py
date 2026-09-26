"""The wiki model: pages, atoms, embeds, rendering, and structural edits.

A *page* is a folder containing `_page.md`. An *atom* is any other `.md` file in
the wiki with frontmatter `id` (a UUID) and `title`. Pages embed atoms with
Obsidian syntax on their own line: `![[atom-file-name]]` (optionally
`![[name|Alias]]` or `![[path/from/wiki/name]]`).
"""

from __future__ import annotations

import datetime as _dt
import re
import uuid as _uuid
from dataclasses import dataclass
from pathlib import Path

from . import frontmatter as fm
from .config import AkitError

PAGE = "_page.md"
ROOT_SPECIAL = {"index.md", "log.md"}
LINK_RE = re.compile(r"(!?)\[\[([^\]|#]+)((?:#[^\]|]*)?)((?:\|[^\]]*)?)\]\]")
EMBED_LINE_RE = re.compile(r"^\s*!\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|([^\]]*))?\]\]\s*$")
HEADING_RE = re.compile(r"^(#{1,6})\s+\S")
FENCE_RE = re.compile(r"^\s*(```|~~~)")
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:80].strip("-") or "atom"


def new_uuid() -> str:
    # uuid4 draws from os.urandom: the ID never comes from the model.
    return str(_uuid.uuid4())


@dataclass
class Problem:
    level: str  # "error" | "warn"
    where: str
    message: str

    def __str__(self) -> str:
        return f"{self.level.upper():5} {self.where}: {self.message}"


class Wiki:
    def __init__(self, root: Path):
        self.root = root.resolve()
        if not self.root.is_dir():
            raise AkitError(f"Wiki folder not found: {self.root}")

    # ---------- scanning ----------

    def rel(self, path: Path) -> str:
        return path.resolve().relative_to(self.root).as_posix()

    def _walk_md(self):
        for p in sorted(self.root.rglob("*.md")):
            parts = p.relative_to(self.root).parts
            if any(part.startswith(".") for part in parts):
                continue
            yield p

    def page_dirs(self) -> list[Path]:
        return sorted({p.parent for p in self._walk_md() if p.name == PAGE}, key=lambda d: self.rel(d))

    def atom_files(self) -> list[Path]:
        out = []
        for p in self._walk_md():
            if p.name == PAGE:
                continue
            if p.parent == self.root and p.name in ROOT_SPECIAL:
                continue
            out.append(p)
        return out

    def atoms(self) -> list[fm.Doc]:
        return [d for d in (fm.load(p) for p in self.atom_files()) if d.id]

    def by_id(self) -> dict[str, list[Path]]:
        m: dict[str, list[Path]] = {}
        for d in self.atoms():
            m.setdefault(d.id, []).append(d.path)
        return m

    def by_name(self) -> dict[str, list[Path]]:
        m: dict[str, list[Path]] = {}
        for p in self.atom_files():
            m.setdefault(p.stem, []).append(p)
        return m

    # ---------- resolution ----------

    def resolve_embed(self, target: str, from_dir: Path) -> Path:
        t = target.strip()
        if t.endswith(".md"):
            t = t[:-3]
        if "/" in t:
            cand = self.root / (t + ".md")
            if cand.is_file():
                return cand
            if (self.root / t / PAGE).is_file():
                return self.root / t / PAGE
            raise AkitError(f"missing: {target}")
        local = from_dir / (t + ".md")
        if local.is_file() and local.name != PAGE:
            return local
        hits = self.by_name().get(t, [])
        if len(hits) == 1:
            return hits[0]
        if not hits:
            raise AkitError(f"missing: {target}")
        raise AkitError(f"ambiguous: {target} matches {', '.join(self.rel(h) for h in hits)}")

    def find(self, ref: str, cwd: Path | None = None) -> Path:
        """Resolve a user reference: UUID, atom name, page dir, or file path."""
        ref = ref.strip()
        if UUID_RE.match(ref.lower()):
            hits = self.by_id().get(ref.lower(), [])
            if len(hits) == 1:
                return hits[0]
            if not hits:
                raise AkitError(f"No atom with id {ref}")
            raise AkitError(f"Duplicate id {ref}: {', '.join(self.rel(h) for h in hits)}")
        for base in [cwd or Path.cwd(), self.root, self.root.parent]:
            p = (base / ref).resolve()
            if p.is_dir() and (p / PAGE).is_file():
                return p / PAGE
            if p.is_file() and p.suffix == ".md":
                return p
            if p.with_suffix(".md").is_file():
                return p.with_suffix(".md")
        hits = self.by_name().get(ref.removesuffix(".md"), [])
        if len(hits) == 1:
            return hits[0]
        if hits:
            raise AkitError(f"Ambiguous name {ref}: {', '.join(self.rel(h) for h in hits)}")
        raise AkitError(f"Not found: {ref}")

    def page_dir(self, ref: str, cwd: Path | None = None) -> Path:
        p = self.find(ref, cwd)
        if p.name != PAGE:
            raise AkitError(f"Not a page: {ref} (pages are folders with {PAGE})")
        return p.parent

    # ---------- rendering ----------

    def render(self, path: Path) -> tuple[str, list[str]]:
        """Return (markdown, errors) with every whole-line embed transcluded."""
        errors: list[str] = []
        doc = fm.load(path)
        if path.name == PAGE:
            head = [f"# {doc.title or self.rel(path.parent) or 'Wiki'}"]
            head.append(f"<!-- page: {self.rel(path.parent) or '.'} -->")
            if doc.meta.get("summary"):
                head.append(f"_{doc.meta['summary']}_")
            body = self._render_body(doc.body, path.parent, 1, [path.resolve()], errors)
            return "\n".join(head) + "\n\n" + body.strip("\n") + "\n", errors
        return self._render_atom(path, 1, [], errors).strip("\n") + "\n", errors

    def _render_body(self, body: str, cur: Path, base: int, stack: list[Path], errors: list[str]) -> str:
        out: list[str] = []
        level = base
        fenced = False
        for line in body.split("\n"):
            if FENCE_RE.match(line):
                fenced = not fenced
                out.append(line)
                continue
            if fenced:
                out.append(line)
                continue
            h = HEADING_RE.match(line)
            if h:
                level = len(h.group(1))
                out.append(line)
                continue
            m = EMBED_LINE_RE.match(line)
            if not m:
                out.append(line)
                continue
            try:
                target = self.resolve_embed(m.group(1), cur)
            except AkitError as e:
                errors.append(f"{self.rel(cur / PAGE) if (cur / PAGE).exists() else self.rel(cur)}: {e}")
                out.append(f"> **MISSING ATOM:** `{m.group(1).strip()}` ({e})")
                continue
            if target.resolve() in stack:
                errors.append(f"cycle: {' -> '.join(self.rel(s) for s in stack)} -> {self.rel(target)}")
                out.append(f"> **CYCLE:** `{m.group(1).strip()}`")
                continue
            if out and out[-1].strip():
                out.append("")
            out.append(self._render_atom(target, min(level + 1, 6), stack, errors))
        return "\n".join(out)

    def _render_atom(self, path: Path, level: int, stack: list[Path], errors: list[str]) -> str:
        doc = fm.load(path)
        title = doc.title or path.stem
        if path.name == PAGE:
            tag = f"<!-- page: {self.rel(path.parent)} -->"
        else:
            tag = f"<!-- atom: {doc.id or 'NO-ID'} · {self.rel(path)} -->"
        if doc.meta.get("status"):
            tag += f"\n**Status:** {doc.meta['status'].upper()}"
        body = _shift_headings(doc.body, level)
        body = self._render_body(body, path.parent, level, [*stack, path.resolve()], errors)
        return f"{'#' * level} {title}\n{tag}\n\n{body.strip()}"

    # ---------- structural edits ----------

    def new_page(self, rel: str, title: str, summary: str = "") -> Path:
        d = self.root / rel.strip("/")
        if (d / PAGE).exists():
            raise AkitError(f"Page already exists: {self.rel(d)}")
        parent = d.parent
        if parent != self.root and not (parent / PAGE).is_file():
            raise AkitError(f"Parent is not a page: {self.rel(parent)}. Create it first.")
        meta = {"title": title}
        if summary:
            meta["summary"] = summary
        fm.save(fm.Doc(path=d / PAGE, meta=meta, body=""))
        return d / PAGE

    def unique_name(self, base: str, taken: set[str] | None = None) -> str:
        taken = taken if taken is not None else set(self.by_name())
        taken |= {"_page", "index", "log"}
        name, n = base, 2
        while name in taken:
            name, n = f"{base}-{n}", n + 1
        return name

    def new_atom(self, title: str, page_dir: Path, body: str = "", name: str | None = None,
                 status: str | None = None, embed: bool = True, after: str | None = None) -> fm.Doc:
        if not (page_dir / PAGE).is_file():
            raise AkitError(f"Not a page: {page_dir}")
        name = self.unique_name(slugify(name or title))
        meta = {"id": new_uuid(), "title": title}
        if status:
            meta["status"] = status
        doc = fm.Doc(path=page_dir / f"{name}.md", meta=meta, body=body)
        fm.save(doc)
        if embed:
            self._insert_embed(page_dir / PAGE, name, after)
        return doc

    def _insert_embed(self, page: Path, name: str, after: str | None) -> None:
        doc = fm.load(page)
        lines = doc.body.split("\n") if doc.body else []
        line = f"![[{name}]]"
        if after:
            after_name = self.find(after).stem
            for i, l in enumerate(lines):
                m = EMBED_LINE_RE.match(l)
                if m and _target_name(m.group(1)) == after_name:
                    lines.insert(i + 1, line)
                    break
            else:
                raise AkitError(f"{after} is not embedded in {self.rel(page)}")
        else:
            while lines and not lines[-1].strip():
                lines.pop()
            lines.append(line)
        doc.body = "\n".join(lines)
        fm.save(doc)

    def rename_atom(self, ref: str, title: str | None, name: str | None = None) -> Path:
        path = self.find(ref)
        if path.name == PAGE:
            raise AkitError("Use this on atoms, not pages.")
        doc = fm.load(path)
        old_title = doc.title
        if title:
            doc.meta["title"] = title
            fm.save(doc)
        new_name = slugify(name) if name else (slugify(title) if title else path.stem)
        if new_name == path.stem:
            return path
        taken = set(self.by_name()) - {path.stem}
        new_name = self.unique_name(new_name, taken)
        new_path = path.with_name(new_name + ".md")
        path.rename(new_path)
        self._rewrite_links(old=path, new=new_path, old_title=old_title, new_title=title)
        return new_path

    def move_atom(self, ref: str, page_dir: Path) -> Path:
        path = self.find(ref)
        if path.name == PAGE:
            raise AkitError("Use this on atoms, not pages.")
        if not (page_dir / PAGE).is_file():
            raise AkitError(f"Not a page: {page_dir}")
        if path.parent.resolve() == page_dir.resolve():
            return path
        new_path = page_dir / path.name
        if new_path.exists():
            raise AkitError(f"{self.rel(new_path)} already exists")
        old_page = path.parent / PAGE
        path.rename(new_path)
        if old_page.is_file():
            self._drop_embed_lines(old_page, path.stem)
        self._rewrite_links(old=path, new=new_path)
        self._insert_embed(page_dir / PAGE, new_path.stem, None)
        return new_path

    def remove_atom(self, ref: str) -> tuple[Path, list[str]]:
        path = self.find(ref)
        if path.name == PAGE:
            raise AkitError("Use this on atoms, not pages.")
        path.unlink()
        leftovers = []
        for md in self._walk_md():
            if self._drop_embed_lines(md, path.stem, path):
                continue
            for m in LINK_RE.finditer(md.read_text(encoding="utf-8")):
                if self._link_points_to(m.group(2), md.parent, path):
                    leftovers.append(self.rel(md))
        return path, sorted(set(leftovers))

    def _link_points_to(self, target: str, from_dir: Path, path: Path) -> bool:
        t = target.strip().removesuffix(".md")
        if "/" in t:
            return (self.root / (t + ".md")).resolve() == path.resolve()
        return t == path.stem

    def _drop_embed_lines(self, md: Path, stem: str, path: Path | None = None) -> bool:
        text = md.read_text(encoding="utf-8")
        kept, dropped = [], False
        for line in text.split("\n"):
            m = EMBED_LINE_RE.match(line)
            if m and (_target_name(m.group(1)) == stem):
                dropped = True
                continue
            kept.append(line)
        if dropped:
            md.write_text("\n".join(kept), encoding="utf-8")
        return dropped

    def _rewrite_links(self, old: Path, new: Path, old_title: str | None = None, new_title: str | None = None) -> None:
        old_rel = (old.parent.resolve().relative_to(self.root) / old.stem).as_posix()
        new_rel = self.rel(new)[:-3]

        def sub(m: re.Match) -> str:
            bang, target, anchor, alias = m.groups()
            t = target.strip().removesuffix(".md")
            if t == old_rel:
                t = new_rel
            elif "/" not in t and t == old.stem:
                t = new.stem
            else:
                return m.group(0)
            if old_title and new_title and alias == f"|{old_title}":
                alias = f"|{new_title}"
            return f"{bang}[[{t}{anchor}{alias}]]"

        for md in self._walk_md():
            text = md.read_text(encoding="utf-8")
            new_text = LINK_RE.sub(sub, text)
            if new_text != text:
                md.write_text(new_text, encoding="utf-8")

    # ---------- index, log, check ----------

    def build_index(self) -> str:
        lines = ["# Index", "", "<!-- Generated by `akit index`. Do not edit by hand; edit page titles/summaries instead. -->", ""]
        for d in self.page_dirs():
            rel = self.rel(d)
            if rel == ".":
                continue
            doc = fm.load(d / PAGE)
            depth = rel.count("/")
            link = f"[{doc.title or rel}]({rel}/{PAGE})"
            extra = f" — {doc.meta['summary']}" if doc.meta.get("summary") else ""
            mark = " 🔖" if doc.meta.get("bookmark") else ""
            lines.append(f"{'  ' * depth}- {link}{extra}{mark}")
        return "\n".join(lines) + "\n"

    def write_index(self) -> Path:
        p = self.root / "index.md"
        p.write_text(self.build_index(), encoding="utf-8")
        return p

    def append_log(self, op: str, subject: str, note: str = "") -> Path:
        p = self.root / "log.md"
        if not p.exists():
            p.write_text("# Log\n\nAppend-only. Newest at the bottom.\n", encoding="utf-8")
        today = _dt.date.today().isoformat()
        entry = f"\n## [{today}] {op} | {subject}\n"
        if note:
            entry += f"\n{note.strip()}\n"
        with p.open("a", encoding="utf-8") as f:
            f.write(entry)
        return p

    def check(self) -> list[Problem]:
        probs: list[Problem] = []
        embedded: set[Path] = set()
        for md in self._walk_md():
            if md.parent == self.root and md.name in ROOT_SPECIAL:
                continue
            doc = fm.load(md)
            where = self.rel(md)
            if md.name == PAGE:
                if not doc.title:
                    probs.append(Problem("error", where, "page has no title"))
                if not doc.meta.get("summary") and md.parent != self.root:
                    probs.append(Problem("warn", where, "page has no summary (index line will be bare)"))
                bm = doc.meta.get("bookmark")
                if bm and not bm.startswith("Use "):
                    probs.append(Problem("error", where, 'bookmark must start with "Use " (e.g. "Use before writing ...")'))
            elif not doc.meta:
                probs.append(Problem("warn", where, "markdown file without frontmatter (not an atom)"))
                continue
            else:
                if not doc.id:
                    probs.append(Problem("error", where, "atom has no id (create atoms with `akit atom new`)"))
                elif not UUID_RE.match(doc.id):
                    probs.append(Problem("error", where, f"id is not a lowercase UUID: {doc.id}"))
                if not doc.title:
                    probs.append(Problem("error", where, "atom has no title"))
            fenced = False
            for line in doc.body.split("\n"):
                if FENCE_RE.match(line):
                    fenced = not fenced
                if fenced:
                    continue
                m = EMBED_LINE_RE.match(line)
                if not m:
                    continue
                try:
                    embedded.add(self.resolve_embed(m.group(1), md.parent).resolve())
                except AkitError as e:
                    probs.append(Problem("error", where, str(e)))
        for i, paths in self.by_id().items():
            if len(paths) > 1:
                probs.append(Problem("error", i, "duplicate id: " + ", ".join(self.rel(p) for p in paths)))
        for n, paths in self.by_name().items():
            if len(paths) > 1:
                probs.append(Problem("error", n, "duplicate atom file name (bare embeds become ambiguous): "
                                     + ", ".join(self.rel(p) for p in paths)))
        for d in self.atoms():
            if d.path.resolve() not in embedded:
                probs.append(Problem("warn", self.rel(d.path), "orphan atom: not embedded in any page"))
        idx = self.root / "index.md"
        if not idx.exists() or idx.read_text(encoding="utf-8") != self.build_index():
            probs.append(Problem("error", "index.md", "stale; run `akit index`"))
        return probs


def _target_name(target: str) -> str:
    return target.strip().removesuffix(".md").split("/")[-1]


def _shift_headings(body: str, level: int) -> str:
    out, fenced = [], False
    for line in body.split("\n"):
        if FENCE_RE.match(line):
            fenced = not fenced
        h = None if fenced else HEADING_RE.match(line)
        if h:
            n = min(len(h.group(1)) + level, 6)
            line = "#" * n + line[len(h.group(1)):]
        out.append(line)
    return "\n".join(out)
