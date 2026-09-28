"""The owner-only sharing flag and the locks that keep agents from changing it.

The flag lives in its own file, `.agent-kit-share.json`, never in `.agent-kit.json`
(which agents edit routinely). akit only ever *creates* it, during `akit init`,
from the owner's answer. After that, only the owner changes it, by hand.

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
from .config import SHARE_FILE, SHARE_MODES, AkitError, Project

SHARE_HELP = {
    "off": "never share anything from this project to the kit",
    "owner": "share only when the owner explicitly asks in the conversation",
    "on": "agents may propose shares; an independent judge gates each one",
}


def share_path(project: Project) -> Path:
    return project.root / SHARE_FILE


def write_share_file(project: Project, mode: str) -> Path:
    """Create the flag file. Refuses to overwrite: after init, only the owner edits it by hand."""
    if mode not in SHARE_MODES:
        raise AkitError(f"share must be one of: {', '.join(SHARE_MODES)}")
    path = share_path(project)
    if path.exists():
        raise AkitError(f"{SHARE_FILE} already exists; only the owner changes it, by hand.")
    data = {
        "share": mode,
        "_meaning": {m: SHARE_HELP[m] for m in SHARE_MODES},
        "_note": "Owner-only setting. Agents must never edit this file. "
                 "If it is locked, unlock it yourself (see `akit config share`), edit, then run `akit lock`.",
        "set": _dt.date.today().isoformat(),
    }
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return path


def ask_share_mode() -> str:
    """Interactive prompt for a human at a terminal."""
    print("\nMay agents share content from this project to the public agent-kit repo?")
    for i, m in enumerate(SHARE_MODES, 1):
        print(f"  {i}. {m:5}  {SHARE_HELP[m]}")
    while True:
        answer = input("Choose 1-3 [1 = off]: ").strip() or "1"
        if answer in {"1", "2", "3"}:
            return SHARE_MODES[int(answer) - 1]
        if answer in SHARE_MODES:
            return answer


# ---------------- locks ----------------

def lock(project: Project) -> list[str]:
    """Apply every lock akit can apply itself. Idempotent; only ever restricts."""
    path = share_path(project)
    if not path.exists():
        raise AkitError(f"No {SHARE_FILE}. Sharing is off until the owner runs `akit init` or creates it.")
    log: list[str] = []
    rel = SHARE_FILE
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
    path = share_path(project)
    if not path.exists():
        return "missing"
    st = path.stat()
    if st.st_uid == 0:
        return "hard-locked (owned by root)"
    if not st.st_mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH):
        return "read-only (agents with a shell could still chmod it; hard-lock for a guarantee)"
    return "writable (run `akit lock`)"


def file_link(project: Project) -> str:
    return share_path(project).resolve().as_uri()


def hard_lock_command(project: Project) -> str:
    p = str(share_path(project).resolve())
    if sys.platform == "win32":
        return f'icacls "{p}" /setowner Administrators && icacls "{p}" /inheritance:r /grant:r Administrators:F /grant:r Users:R'
    return f'sudo chown root "{p}" && sudo chmod 644 "{p}"'


def unlock_steps(project: Project) -> str:
    p = str(share_path(project).resolve())
    user = os.environ.get("USER", "$USER")
    if "root" in status(project):
        pre = f'sudo chown {user} "{p}" && chmod 644 "{p}"'
    else:
        pre = f'chmod 644 "{p}"'
    return (f"  1. {pre}\n"
            f'  2. edit "share" in {p}  (off | owner | on)\n'
            f"  3. akit lock   (and re-run the hard lock if you use one: {hard_lock_command(project)})")


CODEX_SNIPPET = """# Optional, unverified: Codex split permissions keeping the share flag read-only.
# Add to your Codex config and select the profile per Codex docs.
[permissions.akit.filesystem.":project_roots"]
"." = "write"
".agent-kit-share.json" = "read"
"""
