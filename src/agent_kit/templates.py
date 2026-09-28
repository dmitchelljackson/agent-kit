"""Templates: typed page shapes with fields, rules, and an optional skeleton.

A template is a page at `wiki/templates/<name>/`:

  _page.md        the template's rules, as atoms (shown by `akit new <name> --help`)
  template.json   description, path pattern, optional key scheme, and fields
  _skeleton/      optional: `_page.md` body and atoms copied into every new page

Pages made from a template carry `template: <name>` in frontmatter, and their
field values are validated by `akit new`, `akit set`, and `akit check`.
"""

from __future__ import annotations

import datetime as _dt
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import frontmatter as fm
from .config import AkitError
from . import scope as sc
from .wiki import EMBED_LINE_RE, PAGE, Problem, Wiki, new_uuid, slugify

TEMPLATES_DIR = "templates"
SKELETON = "_skeleton"
TYPES = {"string", "text", "enum", "ref", "date", "bool"}
RESERVED = {"title", "summary", "template", "key", "bookmark", "bookmark_approval", "bookmark_name", "id"}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass
class Field:
    name: str
    type: str = "string"
    help: str = ""
    required: bool = False
    default: str | None = None
    values: list[str] = field(default_factory=list)
    multiple: bool = False
    template: str | None = None   # ref: restrict targets to pages of this template
    into: str = "meta"            # meta: frontmatter | atom: becomes an atom on the page
    atom_title: str | None = None

    @property
    def flag(self) -> str:
        return "--" + self.name.replace("_", "-")

    @property
    def is_atom(self) -> bool:
        return self.into == "atom"


@dataclass
class Template:
    name: str
    dir: Path
    description: str
    path: str
    key: dict | None
    fields: dict[str, Field]
    scope: str | None = None


def _field(name: str, spec: dict, where: str) -> Field:
    if name in RESERVED:
        raise AkitError(f"{where}: field name '{name}' is reserved")
    f = Field(name=name, **{k: v for k, v in spec.items() if k in Field.__dataclass_fields__ and k != "name"})
    if f.type not in TYPES:
        raise AkitError(f"{where}: field '{name}' has unknown type '{f.type}' (use {', '.join(sorted(TYPES))})")
    if f.type == "enum" and not f.values:
        raise AkitError(f"{where}: enum field '{name}' needs \"values\"")
    if f.is_atom and f.type != "text":
        raise AkitError(f"{where}: only text fields can go into an atom ('{name}')")
    return f


def load(wiki: Wiki, name_or_dir: str | Path) -> Template:
    d = name_or_dir if isinstance(name_or_dir, Path) else wiki.root / TEMPLATES_DIR / name_or_dir
    spec_path = d / "template.json"
    if not spec_path.is_file():
        raise AkitError(f"No template '{d.name}'. See `akit template ls`.")
    where = wiki.rel(spec_path)
    try:
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise AkitError(f"{where}: invalid JSON: {e}") from e
    fields = {n: _field(n, s, where) for n, s in spec.get("fields", {}).items()}
    return Template(name=d.name, dir=d, description=spec.get("description", ""),
                    path=spec.get("path", d.name + "/{slug}"), key=spec.get("key"), fields=fields,
                    scope=spec.get("scope"))


def all_templates(wiki: Wiki) -> dict[str, Template]:
    base = wiki.root / TEMPLATES_DIR
    if not base.is_dir():
        return {}
    return {d.name: load(wiki, d) for d in sorted(base.iterdir()) if (d / "template.json").is_file()}


def pages_of(wiki: Wiki, name: str) -> list[fm.Doc]:
    out = []
    for d in wiki.page_dirs():
        doc = fm.load(d / PAGE)
        if doc.meta.get("template") == name:
            out.append(doc)
    return out


# ---------------- values ----------------

def split_multi(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


def key_index(wiki: Wiki) -> dict[str, Path]:
    idx: dict[str, Path] = {}
    for d in wiki.page_dirs():
        k = fm.load(d / PAGE).meta.get("key")
        if k:
            idx[k.upper()] = d
    return idx


def resolve_ref(wiki: Wiki, value: str, template: str | None = None, keys: dict[str, Path] | None = None) -> Path:
    keys = keys if keys is not None else key_index(wiki)
    target = keys.get(value.upper())
    if target is None:
        p = wiki.find(value)
        target = p.parent if p.name == PAGE else p
    if template:
        doc = fm.load(target / PAGE) if target.is_dir() else None
        if not doc or doc.meta.get("template") != template:
            raise AkitError(f"'{value}' is not a {template} page")
    return target


def validate_value(wiki: Wiki, f: Field, raw: str | list[str], keys: dict[str, Path] | None = None) -> str:
    items = raw if isinstance(raw, list) else (split_multi(raw) if f.multiple else [raw])
    if not f.multiple and len(items) > 1:
        raise AkitError(f"{f.flag} takes one value")
    out = []
    for v in items:
        v = v.strip()
        if f.type == "enum" and v not in f.values:
            raise AkitError(f"{f.flag}: '{v}' is not one of {', '.join(f.values)}")
        if f.type == "date" and not DATE_RE.match(v):
            raise AkitError(f"{f.flag}: '{v}' is not YYYY-MM-DD")
        if f.type == "bool" and v not in {"yes", "no"}:
            raise AkitError(f"{f.flag}: use yes or no")
        if f.type == "ref":
            try:
                resolve_ref(wiki, v, f.template, keys)
            except AkitError as e:
                raise AkitError(f"{f.flag}: {e}") from e
        out.append(v)
    return ", ".join(out)


def _read_text_arg(value: str) -> str:
    if value.startswith("@"):
        return Path(value[1:]).read_text(encoding="utf-8")
    return value


# ---------------- create ----------------

def next_key(wiki: Wiki, tpl: Template) -> str | None:
    if not tpl.key:
        return None
    prefix, pad = tpl.key.get("prefix", ""), int(tpl.key.get("pad", 3))
    step, start = int(tpl.key.get("step", 1)), int(tpl.key.get("start", tpl.key.get("step", 1)))
    nums = []
    for doc in pages_of(wiki, tpl.name):
        m = re.match(re.escape(prefix) + r"(\d+)$", doc.meta.get("key", ""))
        if m:
            nums.append(int(m.group(1)))
    n = (max(nums) // step + 1) * step if nums else start
    return f"{prefix}{n:0{pad}d}"


def create(wiki: Wiki, tpl: Template, title: str, values: dict[str, object], key: str | None = None) -> Path:
    keys = key_index(wiki)
    key = key or next_key(wiki, tpl)
    if key and key.upper() in keys:
        raise AkitError(f"Key {key} already exists at {wiki.rel(keys[key.upper()])}")
    slug = slugify(title)
    today = _dt.date.today().isoformat()
    ctx = {"key": key or "", "key_lower": (key or "").lower(), "slug": slug, "date": today, "title": title}
    rel = tpl.path.format(**ctx).strip("/")
    page_dir = wiki.root / rel
    if (page_dir / PAGE).exists():
        raise AkitError(f"Page already exists: {rel}")

    meta: dict[str, str] = {"title": title, "template": tpl.name}
    if key:
        meta["key"] = key
    atom_values: dict[str, str] = {}
    for name, f in tpl.fields.items():
        raw = values.get(name)
        if raw in (None, [], ""):
            if f.required:
                raise AkitError(f"{f.flag} is required for {tpl.name} (see `akit new {tpl.name} --help`)")
            if f.default is not None and not f.is_atom:
                meta[name] = f.default
            continue
        if f.is_atom:
            atom_values[name] = _read_text_arg(str(raw))
        else:
            meta[name] = validate_value(wiki, f, raw if isinstance(raw, list) else str(raw), keys)

    # parent pages
    parts = Path(rel).parts
    for i in range(1, len(parts)):
        parent = wiki.root / Path(*parts[:i])
        if not (parent / PAGE).exists():
            wiki.new_page(Path(*parts[:i]).as_posix(), parts[i - 1].replace("-", " ").title(),
                          summary=f"{tpl.name.title()} pages" if i == len(parts) - 1 else "")

    page_dir.mkdir(parents=True, exist_ok=True)
    top = wiki.root / parts[0]
    if tpl.scope and len(parts) > 1 and not (top / sc.SCOPE_FILE).exists():
        sc.write(top, tpl.scope)  # e.g. tickets/ -> main, the first time a ticket is made
    skel = tpl.dir / SKELETON
    body = ""
    renames: dict[str, str] = {}
    if skel.is_dir():
        if (skel / PAGE).exists():
            body = fm.load(skel / PAGE).body
        taken = set(wiki.by_name())
        for f in sorted(skel.glob("*.md")):
            if f.name == PAGE:
                continue
            sdoc = fm.load(f)
            name = wiki.unique_name(f"{slug}-{f.stem}", taken)
            taken.add(name)
            renames[f.stem] = name
            smeta = {"id": new_uuid(), "title": _fill(sdoc.meta.get("title", f.stem.replace("-", " ").capitalize()), ctx)}
            smeta.update({k: v for k, v in sdoc.meta.items() if k not in ("id", "title")})
            fm.save(fm.Doc(path=page_dir / f"{name}.md", meta=smeta, body=_fill(sdoc.body, ctx)))
    body = _fill(body, ctx)
    for old, new in renames.items():
        body = re.sub(r"(!\[\[)" + re.escape(old) + r"(\]\]|\|)", lambda m: m.group(1) + new + m.group(2), body)

    taken = set(wiki.by_name())
    for name, text in atom_values.items():
        f = tpl.fields[name]
        aname = wiki.unique_name(f"{slug}-{name.replace('_', '-')}", taken)
        taken.add(aname)
        atitle = f.atom_title or name.replace("_", " ").capitalize()
        fm.save(fm.Doc(path=page_dir / f"{aname}.md", meta={"id": new_uuid(), "title": atitle}, body=text))
        placeholder = "{{field:" + name + "}}"
        if placeholder in body:
            body = body.replace(placeholder, f"![[{aname}]]")
        else:
            body = body.rstrip("\n") + f"\n\n![[{aname}]]\n"
    body = re.sub(r"^\s*\{\{field:[a-z_]+\}\}\s*$\n?", "", body, flags=re.M)  # unused atom slots
    for name in tpl.fields:
        body = body.replace("{{field:" + name + "}}", meta.get(name, ""))
    fm.save(fm.Doc(path=page_dir / PAGE, meta=meta, body=body))
    return page_dir


def _fill(text: str, ctx: dict) -> str:
    for k, v in ctx.items():
        text = text.replace("{{" + k + "}}", v)
    return text


# ---------------- set / query ----------------

def set_fields(wiki: Wiki, ref: str, assignments: list[str]) -> tuple[Path, dict[str, str]]:
    page_dir = resolve_ref(wiki, ref)
    if not page_dir.is_dir():
        raise AkitError(f"{ref} is an atom; `akit set` works on pages made from templates")
    doc = fm.load(page_dir / PAGE)
    name = doc.meta.get("template")
    if not name:
        raise AkitError(f"{wiki.rel(page_dir)} wasn't made from a template")
    tpl = load(wiki, name)
    changed = {}
    for a in assignments:
        k, sep, v = a.partition("=")
        k = k.strip().lstrip("-").replace("-", "_")
        if not sep:
            raise AkitError(f"Use field=value (got '{a}')")
        if k not in tpl.fields or tpl.fields[k].is_atom:
            meta_fields = [n for n, f in tpl.fields.items() if not f.is_atom]
            raise AkitError(f"'{k}' is not a settable field of {name}. Fields: {', '.join(meta_fields)}")
        if v == "":
            if tpl.fields[k].required:
                raise AkitError(f"{k} is required")
            doc.meta.pop(k, None)
        else:
            doc.meta[k] = validate_value(wiki, tpl.fields[k], v)
        changed[k] = v
    fm.save(doc)
    return page_dir, changed


def query(wiki: Wiki, name: str, where: list[str]) -> list[fm.Doc]:
    tpl = load(wiki, name)
    conds = []
    for w in where:
        m = re.match(r"^([a-z_]+)\s*(!=|=)\s*(.*)$", w.strip())
        if not m:
            raise AkitError(f"Bad --where '{w}' (use field=value or field!=value)")
        k, op, v = m.groups()
        if k not in tpl.fields and k not in {"key", "title"}:
            raise AkitError(f"{name} has no field '{k}'")
        conds.append((k, op, v))

    def match(doc: fm.Doc) -> bool:
        for k, op, v in conds:
            f = tpl.fields.get(k)
            actual = doc.meta.get(k, "")
            vals = split_multi(actual) if f and f.multiple else [actual]
            hit = v in vals
            if (op == "=") != hit:
                return False
        return True

    rows = [d for d in pages_of(wiki, name) if match(d)]
    return sorted(rows, key=lambda d: (d.meta.get("key", ""), d.title))


# ---------------- templates from pages, validation ----------------

def from_page(wiki: Wiki, name: str, page_dir: Path, description: str) -> Path:
    name = slugify(name)
    d = wiki.root / TEMPLATES_DIR / name
    if d.exists():
        raise AkitError(f"Template '{name}' already exists")
    if not (wiki.root / TEMPLATES_DIR / PAGE).exists():
        wiki.new_page(TEMPLATES_DIR, "Templates", "Typed page shapes: fields, rules, and skeletons. `akit new --help` lists them.")
    src = fm.load(page_dir / PAGE)
    fields = {k: {"type": "string", "help": "TODO: describe; pick a type"} for k in src.meta
              if k not in RESERVED}
    parent = wiki.rel(page_dir.parent)
    spec = {"description": description or f"TODO: what a {name} page is for",
            "path": (f"{parent}/{{slug}}" if parent != "." else "{slug}"), "fields": fields}
    wiki.new_page(f"{TEMPLATES_DIR}/{name}", f"{name.replace('-', ' ').title()} template",
                  summary=description or f"Rules for {name} pages")
    (d / "template.json").write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")
    skel = d / SKELETON
    skel.mkdir()
    body = src.body
    for f in sorted(page_dir.glob("*.md")):
        if f.name == PAGE:
            continue
        adoc = fm.load(f)
        generic = f.stem
        fm.save(fm.Doc(path=skel / f"{generic}.md", meta={"title": adoc.title}, body="TODO: guidance for this part"))
    fm.save(fm.Doc(path=skel / PAGE, meta={}, body=body))
    src.meta["template"] = name
    fm.save(src)
    return d


def validate(wiki: Wiki) -> list[Problem]:
    probs: list[Problem] = []
    try:
        tpls = all_templates(wiki)
    except AkitError as e:
        return [Problem("error", "templates", str(e))]
    keys: dict[str, list[Path]] = {}
    for d in wiki.page_dirs():
        doc = fm.load(d / PAGE)
        if doc.meta.get("key"):
            keys.setdefault(doc.meta["key"].upper(), []).append(d)
        name = doc.meta.get("template")
        if not name:
            continue
        where = wiki.rel(d / PAGE)
        tpl = tpls.get(name)
        if not tpl:
            probs.append(Problem("error", where, f"unknown template '{name}'"))
            continue
        for fname, f in tpl.fields.items():
            if f.is_atom:
                continue
            v = doc.meta.get(fname)
            if not v:
                if f.required:
                    probs.append(Problem("error", where, f"missing required field '{fname}'"))
                continue
            try:
                validate_value(wiki, f, v)
            except AkitError as e:
                probs.append(Problem("error", where, str(e)))
        if tpl.scope:
            actual, _ = sc.effective(wiki.root, d)
            if actual != tpl.scope:
                probs.append(Problem("warn", where, f"{name} pages belong in {tpl.scope}-scoped directories; "
                                     f"this one is {sc.describe(wiki.root, d)}"))
        for k in doc.meta:
            if k not in RESERVED and k not in tpl.fields:
                probs.append(Problem("warn", where, f"field '{k}' isn't in the {name} template"))
    for k, dirs in keys.items():
        if len(dirs) > 1:
            probs.append(Problem("error", k, "duplicate key: " + ", ".join(wiki.rel(x) for x in dirs)))
    return probs


def help_epilog(wiki: Wiki, tpl: Template) -> str:
    lines = []
    if tpl.description:
        lines.append(tpl.description)
    lines.append(f"Creates: {tpl.path}" + (f"  (key: {tpl.key.get('prefix', '')}NNN, assigned automatically)" if tpl.key else ""))
    lines.append("Text fields accept @path to read the value from a file.")
    rules, errors = wiki.render(tpl.dir / PAGE)
    lines.append("\n" + "=" * 70 + "\nRULES (from " + wiki.rel(tpl.dir) + ")\n" + "=" * 70 + "\n")
    lines.append(rules)
    if errors:
        lines.append("broken embeds in rules page: " + "; ".join(errors))
    return "\n".join(lines)
