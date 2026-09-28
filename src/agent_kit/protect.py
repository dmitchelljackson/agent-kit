"""Owner-only settings and the locks that keep agents from changing them.

`.agent-kit-owner.json` holds decisions that belong to the owner, never to an agent:

  share:   off | owner | on      may this project's content go to the public kit?
  landing: open | scoped | pr    how may agents get wiki changes onto main?

It is separate from `.agent-kit.json` (which agents edit routinely). akit only ever
*creates* it, during `akit init`, from the owner's answers. After that, only the
owner changes it, by hand.

Layers of protection, weakest to strongest:
  1. Agent permission rules, per adapter (Claude Code deny rules, OpenCode edit
     permissions). The agent's own tool refuses the edit and says why.
  2. Read-only file mode (chmod 444).
  3. Optional hard lock: the owner runs `sudo chown root <file>`. No agent running
     as the owner's user can modify it after that.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import stat
import sys
from pathlib import Path

from . import adapters
from .config import LANDING_MODES, OWNER_FILE, SHARE_MODES, AkitError, Project

SHARE_HELP = {
    "off": "never share anything from this project to the kit",
    "owner": "share only when the owner explicitly asks in the conversation",
    "on": "agents may propose shares; an independent judge gates each one",
}
LANDING_HELP = {
    "open": "no scoping: `akit land` pushes every wiki change to main (solo projects)",
    "scoped": "`akit land` pushes only main-scoped directories; branch-scoped pages ride with the branch",
    "pr": "like scoped, but main-scoped changes go through one rolling PR instead of straight to main",
}
SETTINGS = {"share": (SHARE_MODES, SHARE_HELP), "landing": (LANDING_MODES, LANDING_HELP)}


def owner_path(project: Project) -> Path:
    return project.root / OWNER_FILE


def write_owner_file(project: Project, share: str, landing: str) -> Path:
    """Create the owner file. Refuses to overwrite: after init, only the owner edits it by hand."""
    for key, value in (("share", share), ("landing", landing)):
        modes = SETTINGS[key][0]
        if value not in modes:
            raise AkitError(f"{key} must be one of: {', '.join(modes)}")
    path = owner_path(project)
    if path.exists():
        raise AkitError(f"{OWNER_FILE} already exists; only the owner changes it, by hand.")
    data = {
        "share": share,
        "landing": landing,
        "_meaning": {k: helps for k, (_, helps) in SETTINGS.items()},
        "_note": "Owner-only settings. Agents must never edit this file. "
                 "If it is locked, unlock it yourself (see `akit config`), edit, then run `akit lock`.",
        "set": _dt.date.today().isoformat(),
    }
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return path


def ask(key: str, question: str, default: str) -> str:
    """Interactive prompt for a human at a terminal."""
    modes, helps = SETTINGS[key]
    print(f"\n{question}")
    for i, m in enumerate(modes, 1):
        print(f"  {i}. {m:7} {helps[m]}")
    d = modes.index(default) + 1
    while True:
        answer = input(f"Choose 1-{len(modes)} [{d} = {default}]: ").strip() or str(d)
        if answer.isdigit() and 1 <= int(answer) <= len(modes):
            return modes[int(answer) - 1]
        if answer in modes:
            return answer


# ---------------- locks ----------------

def lock(project: Project) -> list[str]:
    """Apply every lock akit can apply itself. Idempotent; only ever restricts."""
    path = owner_path(project)
    if not path.exists():
        raise AkitError(f"No {OWNER_FILE}. Until the owner runs `akit init`, sharing is off and landing is pr.")
    log: list[str] = []
    rel = OWNER_FILE
    for name in project.agents:
        kind = (adapters.get(name, project).get("protect") or {}).get("type")
        if kind == "claude-settings":
            log += _claude(project.root, rel)
        elif kind == "opencode-json":
            log += _opencode(project.root, rel)
        # other agents: no per-file rule akit can set; the file locks below cover them
    if path.stat().st_uid != 0:
        try:
            mode = path.stat().st_mode
            if mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH):
                path.chmod(mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))
                log.append(f"made {rel} read-only")
        except PermissionError:
            pass
    return log


def _claude(root: Path, rel: str) -> list[str]:
    settings = root / ".claude" / "settings.json"
    data = json.loads(settings.read_text(encoding="utf-8")) if settings.exists() else {}
    deny = data.setdefault("permissions", {}).setdefault("deny", [])
    rules = [f"Edit(/{rel})", f"Write(/{rel})"]
    added = [r for r in rules if r not in deny]
    if not added:
        return []
    deny.extend(added)
    settings.parent.mkdir(parents=True, exist_ok=True)
    settings.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return [f"claude: denied edits to {rel} in .claude/settings.json"]


def _opencode(root: Path, rel: str) -> list[str]:
    cfg = root / "opencode.json"
    data = json.loads(cfg.read_text(encoding="utf-8")) if cfg.exists() else {"$schema": "https://opencode.ai/config.json"}
    perm = data.setdefault("permission", {})
    edit = perm.get("edit", "allow")
    if isinstance(edit, str):
        edit = {"*": edit}
    if edit.get(rel) == "deny" and list(edit)[-1] == rel:
        return []
    edit.pop(rel, None)
    edit[rel] = "deny"  # last matching rule wins, so keep it last
    perm["edit"] = edit
    cfg.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return [f"opencode: denied edits to {rel} in opencode.json"]


def status(project: Project) -> str:
    path = owner_path(project)
    if not path.exists():
        return "missing"
    st = path.stat()
    if st.st_uid == 0:
        return "hard-locked (owned by root)"
    if not st.st_mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH):
        return "read-only (agents with a shell could still chmod it; hard-lock for a guarantee)"
    return "writable (run `akit lock`)"


def file_link(project: Project) -> str:
    return owner_path(project).resolve().as_uri()


def hard_lock_command(project: Project) -> str:
    p = str(owner_path(project).resolve())
    if sys.platform == "win32":
        return f'icacls "{p}" /setowner Administrators && icacls "{p}" /inheritance:r /grant:r Administrators:F /grant:r Users:R'
    return f'sudo chown root "{p}" && sudo chmod 644 "{p}"'


def unlock_steps(project: Project) -> str:
    p = str(owner_path(project).resolve())
    user = os.environ.get("USER", "$USER")
    if "root" in status(project):
        pre = f'sudo chown {user} "{p}" && chmod 644 "{p}"'
    else:
        pre = f'chmod 644 "{p}"'
    return (f"  1. {pre}\n"
            f'  2. edit {p}  ("share": off | owner | on, "landing": open | scoped | pr)\n'
            f"  3. akit lock   (and re-run the hard lock if you use one: {hard_lock_command(project)})")


CODEX_SNIPPET = """# Optional, unverified: Codex split permissions keeping the owner settings read-only.
# Add to your Codex config and select the profile per Codex docs.
[permissions.akit.filesystem.":project_roots"]
"." = "write"
".agent-kit-owner.json" = "read"
"""
