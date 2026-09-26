"""Agent adapter registry: where each agent reads skills/instructions, and how to run it as a judge.

Built-ins live in adapters.json. Projects (`.agent-kit.json`) and users
(`~/.config/akit/config.json`) can override or add agents under "adapters",
e.g. to fill in Grok's judge command, without changing akit.
"""

from __future__ import annotations

import json
from importlib import resources

from .config import AkitError, Project, user_config


def registry(project: Project | None = None) -> dict[str, dict]:
    data = json.loads(resources.files("agent_kit").joinpath("adapters.json").read_text(encoding="utf-8"))
    data.pop("_comment", None)
    for layer in [user_config().get("adapters", {}), (project.data.get("adapters", {}) if project else {})]:
        for name, spec in layer.items():
            data[name] = {**data.get(name, {}), **spec}
    return data


def get(name: str, project: Project | None = None) -> dict:
    reg = registry(project)
    if name not in reg:
        raise AkitError(f"Unknown agent '{name}'. Known: {', '.join(reg)}. Add it under \"adapters\" in .agent-kit.json.")
    return reg[name]
