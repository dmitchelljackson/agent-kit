"""`akit init`: lay down the project skeleton (config, AGENTS.md, wiki, raw)."""

from __future__ import annotations

import json
import re
from importlib import resources
from pathlib import Path

from . import adapters
from .config import CONFIG_NAME, DEFAULT_KIT, AkitError, Project

BEGIN, END = "<!-- akit:begin", "<!-- akit:end -->"


def template(name: str) -> str:
    return resources.files("agent_kit").joinpath("templates", name).read_text(encoding="utf-8")


def akit_block(wiki: str) -> str:
    return template("akit-block.md").replace("{{WIKI}}", wiki).strip()


def upsert_block(text: str, block: str) -> str:
    pattern = re.compile(re.escape(BEGIN) + r".*?" + re.escape(END), re.S)
    if pattern.search(text):
        return pattern.sub(lambda _: block, text)
    return text.rstrip("\n") + "\n\n" + block + "\n"


def init(root: Path, name: str, summary: str, agents: list[str], kit: str, wiki: str, force: bool) -> tuple[Project, list[str]]:
    log: list[str] = []
    cfg = root / CONFIG_NAME
    if cfg.exists() and not force:
        raise AkitError(f"{CONFIG_NAME} already exists. Use --force to re-run init (it won't overwrite your content).")
    for a in agents:
        adapters.get(a)  # validate names early
    project = Project(root=root, data={"project": name, "kit": kit or DEFAULT_KIT, "kit_ref": "main",
                                       "wiki": wiki, "agents": agents})
    if cfg.exists():
        old = Project(root=root, data=json.loads(cfg.read_text()))
        project.data = {**old.data, **{k: v for k, v in project.data.items() if v}}
    project.save()
    log.append(f"wrote {CONFIG_NAME}")

    block = akit_block(wiki)
    agents_md = root / "AGENTS.md"
    if agents_md.exists():
        agents_md.write_text(upsert_block(agents_md.read_text(encoding="utf-8"), block), encoding="utf-8")
        log.append("updated akit block in AGENTS.md")
    else:
        text = (template("AGENTS.md").replace("{{PROJECT}}", name)
                .replace("{{SUMMARY}}", summary or "<!-- TODO(bootstrap): one or two sentences: what this is, and the stack. -->")
                .replace("{{AKIT_BLOCK}}", block))
        agents_md.write_text(text, encoding="utf-8")
        log.append("wrote AGENTS.md")

    for a in agents:
        shim = adapters.get(a, project).get("instructions_file")
        if not shim or shim == "AGENTS.md":
            continue
        p = root / shim
        if not p.exists():
            p.write_text("@AGENTS.md\n", encoding="utf-8")
            log.append(f"wrote {shim} (imports AGENTS.md)")
        elif "@AGENTS.md" not in p.read_text(encoding="utf-8"):
            with p.open("a", encoding="utf-8") as f:
                f.write("\n@AGENTS.md\n")
            log.append(f"appended @AGENTS.md to {shim}")

    w = root / wiki
    w.mkdir(parents=True, exist_ok=True)
    if not (w / "_page.md").exists():
        (w / "_page.md").write_text(template("wiki-page.md").replace("{{PROJECT}}", name), encoding="utf-8")
        log.append(f"wrote {wiki}/_page.md")
    if not (w / "log.md").exists():
        (w / "log.md").write_text("# Log\n\nAppend-only. Newest at the bottom. Entries: `## [YYYY-MM-DD] <op> | <subject>`.\n", encoding="utf-8")
        log.append(f"wrote {wiki}/log.md")
    raw = root / "raw"
    raw.mkdir(exist_ok=True)
    if not (raw / "README.md").exists():
        (raw / "README.md").write_text(template("raw-readme.md"), encoding="utf-8")
        log.append("wrote raw/README.md")

    _ensure_line(root / ".gitattributes", f"{wiki}/log.md merge=union", log)
    _ensure_line(root / ".gitignore", ".obsidian/", log)
    return project, log


def _ensure_line(path: Path, line: str, log: list[str]) -> None:
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    if line in text.split("\n"):
        return
    path.write_text(text + ("" if not text or text.endswith("\n") else "\n") + line + "\n", encoding="utf-8")
    log.append(f"added `{line}` to {path.name}")
