"""Judges: an independent, fresh-context check before a bookmark or a share.

akit builds a *packet* (criteria + context + candidate) and runs it through a
headless agent. Which agent, in priority order:

  1. `--judge NAME|COMMAND` on the command line
  2. `AKIT_JUDGE` environment variable
  3. `"judge"` in .agent-kit.json, then in ~/.config/akit/config.json
  4. the first agent in the project's `agents` list whose adapter has a judge command

A NAME refers to an adapter (claude, codex, opencode, ...); anything else is
treated as a raw shell command. `{file}` in a command is replaced with the
packet path; otherwise the packet is piped on stdin. With no judge available,
akit writes the packet to a file so the calling agent can hand it to a fresh
subagent and re-run with `--verdict`.
"""

from __future__ import annotations

import datetime as _dt
import os
import re
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path

from . import adapters
from .config import AkitError, Project, cache_dir, user_config

ACCEPT = {"bookmark": "approve", "share": "share"}
VERDICTS = {
    "bookmark": ["approve", "revise", "merge-into", "reject"],
    "share": ["share", "revise", "keep-local"],
}
VERDICT_RE = re.compile(r"^\W*VERDICT\W*:\s*([a-z-]+)\s*[:\-—]?\s*(.*?)\W*$", re.I | re.M)


@dataclass
class Verdict:
    word: str
    reason: str

    @property
    def accepted(self) -> bool:
        return self.word in ACCEPT.values()

    @property
    def text(self) -> str:
        return f"{self.word}: {self.reason}" if self.reason else self.word


def parse_verdict(kind: str, text: str) -> Verdict:
    matches = VERDICT_RE.findall(text)
    if matches:
        word, reason = matches[-1]
    else:
        word, _, reason = text.strip().partition(":")
    word = word.strip().lower()
    if word not in VERDICTS[kind]:
        raise AkitError(f"Unrecognized {kind} verdict '{word}'. Expected one of: {', '.join(VERDICTS[kind])}")
    return Verdict(word, reason.strip())


def build_packet(kind: str, criteria: str, candidate: str, context: str) -> str:
    words = " | ".join(VERDICTS[kind])
    return f"""# {kind.title()} judge

You are an independent judge running in a fresh context. You have not seen the
reasoning of the agent that proposed this, and you must not modify any files.
Judge only the candidate below against the criteria. Be strict: approving weak
candidates costs every future session context and attention.

## Criteria

{criteria.strip()}

## Context

{context.strip() or "(none)"}

## Candidate

{candidate.strip()}

## Output

Go through each criterion briefly (pass/fail + one line). Then end with exactly
one final line of the form:

VERDICT: <{words}>: <one-sentence reason, or the specific fix>
"""


def resolve_command(project: Project | None, explicit: str | None = None) -> tuple[str, str] | None:
    """Return (label, shell command) for the judge, or None if nothing is configured."""
    choice = (explicit or os.environ.get("AKIT_JUDGE")
              or (project.data.get("judge") if project else None)
              or user_config().get("judge"))
    reg = adapters.registry(project)
    if choice:
        if choice in reg:
            cmd = reg[choice].get("judge")
            if not cmd:
                raise AkitError(f"Agent '{choice}' has no judge command yet. Set adapters.{choice}.judge in .agent-kit.json.")
            return choice, cmd
        return "custom", choice
    for name in (project.agents if project else []):
        cmd = reg.get(name, {}).get("judge")
        if cmd:
            return name, cmd
    return None


def run(kind: str, packet: str, project: Project | None, explicit: str | None = None) -> tuple[Verdict | None, str]:
    """Run the judge. Returns (verdict, output) or (None, packet_path) when no judge is available."""
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    path = cache_dir() / f"judge-{kind}-{stamp}.md"
    path.write_text(packet, encoding="utf-8")
    resolved = resolve_command(project, explicit)
    if not resolved:
        return None, str(path)
    label, cmd = resolved
    uses_file = "{file}" in cmd
    cmd = cmd.replace("{file}", shlex.quote(str(path)))
    print(f"akit: running {kind} judge via {label}: {cmd}", flush=True)
    try:
        proc = subprocess.run(cmd, shell=True, input=None if uses_file else packet,
                              capture_output=True, text=True, timeout=900,
                              cwd=project.root if project else None)
    except subprocess.TimeoutExpired as e:
        raise AkitError(f"Judge timed out after 15 minutes: {cmd}") from e
    out = proc.stdout.strip()
    if proc.returncode:
        raise AkitError(f"Judge command failed ({proc.returncode}): {cmd}\n{(out + proc.stderr)[-2000:]}")
    return parse_verdict(kind, out), out


NO_JUDGE_HELP = """No judge agent is configured, so akit wrote the judge packet to:

  {path}

Give that file's full contents to a FRESH subagent (no access to this
conversation) and ask it to follow it. Then re-run this command adding:

  --verdict "<the subagent's final VERDICT line>"

To let akit run judges itself, list your agents in .agent-kit.json
("agents": ["claude", ...]) or set AKIT_JUDGE=claude|codex|opencode|<command>.
If the owner explicitly asked for this in the conversation, use --owner instead."""


def criteria_text(wiki_roots: list[Path], kind: str) -> str:
    """Judge criteria come from the wiki itself (project copy first, then the kit)."""
    from .wiki import PAGE, Wiki

    for root in wiki_roots:
        page = root / "agent-kit" / "judges" / kind / PAGE
        if page.is_file():
            text, errors = Wiki(root).render(page)
            if errors:
                raise AkitError("Judge page has broken embeds:\n  " + "\n  ".join(errors))
            return text
    raise AkitError(f"Judge criteria page agent-kit/judges/{kind} not found in the wiki. Run `akit install agent-kit --recursive`.")


def decide(kind: str, packet, project: Project, owner: bool, verdict: str | None,
           judge: str | None) -> str:
    """Gate an action. Returns the approval string to record, or raises."""
    if owner:
        return "owner"
    if verdict:
        v = parse_verdict(kind, verdict)
    else:
        v, out = run(kind, packet() if callable(packet) else packet, project, judge)
        if v is None:
            raise _NoJudge(out)
        print(out)
    if not v.accepted:
        raise AkitError(f"{kind.title()} judge said: {v.text}\nNot proceeding. Fix and retry, or the owner can override with --owner.")
    return f"judge: {v.text}"


class _NoJudge(AkitError):
    exit_code = 3

    def __init__(self, path: str):
        super().__init__(NO_JUDGE_HELP.format(path=path))
