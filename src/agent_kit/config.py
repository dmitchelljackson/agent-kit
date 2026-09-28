"""Project config (`.agent-kit.json`) and user config (`~/.config/akit/config.json`)."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_NAME = ".agent-kit.json"
DEFAULT_KIT = "https://github.com/dmitchelljackson/agent-kit"
SHARE_FILE = ".agent-kit-share.json"  # owner-only; see protect.py
SHARE_MODES = ["off", "owner", "on"]  # least to most permissive


class AkitError(Exception):
    """A user-facing error; printed without a traceback."""

    exit_code = 1


@dataclass
class Project:
    root: Path
    data: dict = field(default_factory=dict)

    @property
    def is_kit(self) -> bool:
        return self.data.get("role") == "kit"

    @property
    def wiki(self) -> Path:
        return self.root / self.data.get("wiki", "wiki")

    @property
    def agents(self) -> list[str]:
        return list(self.data.get("agents", []))

    @property
    def kit_url(self) -> str:
        return self.data.get("kit", DEFAULT_KIT)

    @property
    def kit_ref(self) -> str:
        return self.data.get("kit_ref", "main")

    @property
    def commit(self) -> str | None:
        return self.data.get("commit")

    @property
    def name(self) -> str:
        return self.data.get("project") or self.root.name

    @property
    def share_mode(self) -> str:
        """From the owner-only flag file. Missing or unreadable means off."""
        path = self.root / SHARE_FILE
        if not path.is_file():
            return "off"
        try:
            value = json.loads(path.read_text(encoding="utf-8")).get("share", "off")
        except (json.JSONDecodeError, OSError):
            return "off"
        return _valid_share(value, SHARE_FILE)

    def save(self) -> None:
        (self.root / CONFIG_NAME).write_text(json.dumps(self.data, indent=2) + "\n", encoding="utf-8")


def find_project(start: Path | None = None) -> Project:
    here = (start or Path.cwd()).resolve()
    for d in [here, *here.parents]:
        cfg = d / CONFIG_NAME
        if cfg.is_file():
            return Project(root=d, data=json.loads(cfg.read_text(encoding="utf-8")))
    raise AkitError(f"No {CONFIG_NAME} found here or in any parent. Run `akit init` first.")


def user_config() -> dict:
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    path = base / "akit" / "config.json"
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def cache_dir() -> Path:
    base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    d = base / "agent-kit"
    d.mkdir(parents=True, exist_ok=True)
    return d


def kit_dir_override() -> Path | None:
    value = os.environ.get("AKIT_KIT_DIR") or user_config().get("kit_dir")
    return Path(value).expanduser() if value else None


def _valid_share(mode: str, where: str) -> str:
    if mode not in SHARE_MODES:
        raise AkitError(f"Invalid share mode '{mode}' in {where}; use one of: {', '.join(SHARE_MODES)}")
    return mode


def effective_share_mode(project: Project) -> tuple[str, str]:
    """(mode, source). The stricter of the project and user settings wins."""
    mode, source = project.share_mode, SHARE_FILE
    user = user_config().get("share")
    if user is not None:
        user = _valid_share(user, "~/.config/akit/config.json")
        if SHARE_MODES.index(user) < SHARE_MODES.index(mode):
            mode, source = user, "~/.config/akit/config.json"
    return mode, source
