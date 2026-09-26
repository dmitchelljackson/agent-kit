---
id: ae1ab741-247e-4ea9-99fb-f835d257d261
title: Agent-agnostic by design
---

Everything is plain files: `AGENTS.md`, markdown pages, and `SKILL.md` folders. Agents that read another
instructions file get a one-line shim that imports `AGENTS.md` (e.g. `CLAUDE.md`, `GEMINI.md`).
`akit adapters` lists the registry: skills folder, instructions file, and headless judge command per agent.
Defaults cover Claude Code, Codex, and OpenCode; Gemini, Grok, Cursor, and Copilot have slots.
