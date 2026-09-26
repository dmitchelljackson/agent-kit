"""Minimal YAML-ish frontmatter: flat `key: value` string pairs, order preserved.

Deliberately tiny so akit has no dependencies. Values are strings; double-quoted
values are parsed as JSON strings so they round-trip safely.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

_SAFE = re.compile(r"^[A-Za-z0-9 _.,()/@+-]*$")


@dataclass
class Doc:
    path: Path
    meta: dict[str, str] = field(default_factory=dict)
    body: str = ""

    @property
    def title(self) -> str:
        return self.meta.get("title", "")

    @property
    def id(self) -> str:
        return self.meta.get("id", "")


def parse(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n") and text.strip() != "---":
        return {}, text
    lines = text.split("\n")
    meta: dict[str, str] = {}
    for i in range(1, len(lines)):
        line = lines[i]
        if line.strip() == "---":
            body = "\n".join(lines[i + 1 :])
            return meta, body.lstrip("\n")
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, sep, value = line.partition(":")
        if not sep:
            continue
        meta[key.strip()] = _unquote(value.strip())
    return {}, text  # unterminated frontmatter: treat as plain text


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] == '"':
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value[1:-1]
    if len(value) >= 2 and value[0] == value[-1] == "'":
        return value[1:-1].replace("''", "'")
    return value


def _quote(value: str) -> str:
    if value and _SAFE.match(value) and value == value.strip() and not value[0] in "-@":
        return value
    return json.dumps(value, ensure_ascii=False)


def dump(meta: dict[str, str], body: str) -> str:
    head = "\n".join(f"{k}: {_quote(v)}" for k, v in meta.items())
    body = body.strip("\n")
    return f"---\n{head}\n---\n\n{body}\n" if body else f"---\n{head}\n---\n"


def load(path: Path) -> Doc:
    meta, body = parse(path.read_text(encoding="utf-8"))
    return Doc(path=path, meta=meta, body=body)


def save(doc: Doc) -> None:
    doc.path.parent.mkdir(parents=True, exist_ok=True)
    doc.path.write_text(dump(doc.meta, doc.body), encoding="utf-8")
