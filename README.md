# agent-kit

One place to keep how I like agents to work: rules, reference, and tools, shared across every
project, for any coding agent.

Point an agent at this repo on a new project and it walks you through setup:

> Follow https://github.com/dmitchelljackson/agent-kit/blob/main/BOOTSTRAP.md to set up this project.

## The model

- **Atoms**: one markdown file per piece of knowledge (a rule, a decision, a BDD case, a tool),
  with a permanent UUID and a title. Created by `akit`, never by hand.
- **Pages**: folders with a `_page.md` that arranges atoms with embeds (`![[atom-name]]`).
  Pages nest like Notion. `akit read <page>` assembles the full page for an agent; Obsidian
  renders it for humans.
- **Wiki**: the tree of pages, maintained by agents in the style of
  [Karpathy's LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f):
  immutable `raw/` sources, an index, an append-only log.
- **Templates**: typed page shapes (ticket, bdd, setup, source, tool) with fields, rules, and a
  skeleton. Fields become CLI flags; rules print with `--help`; `akit check` validates.
- **Bookmarks**: skills generated from a page's `bookmark:` field that remind agents to read that
  page at the moment it matters ("Use before writing Kotlin unit tests").
- **Judges**: independent, fresh-context agents that check a bookmark or share is warranted.
  The owner always has final say (`--owner`).
- **Sharing**: projects own their copies and may differ from the kit. `akit sync` reports upstream
  changes to take or skip; `akit share` sends improvements back as PRs. Whether a project may share
  at all (`off` / `owner` / `on`) is the owner's call, kept in a locked file agents can't change.

Agent-agnostic: plain files, `AGENTS.md`, and `SKILL.md` folders. Adapters for Claude Code, Codex,
and OpenCode by default; slots for Gemini, Grok, Cursor, Copilot (`akit adapters`).

## Install

```bash
uv tool install git+https://github.com/dmitchelljackson/agent-kit
```

## Commands

| Command | What it does |
|---|---|
| `akit init` | Set up a project: config, `AGENTS.md`, `wiki/`, `raw/`, kit conventions |
| `akit read <page>` | Print a page with every atom inlined |
| `akit page new <path> "Title"` | Create a page |
| `akit atom new "Title" --page <page>` | Create an atom (UUID generated) and embed it |
| `akit atom find/rename/move/rm` | Restructure atoms without breaking embeds |
| `akit new <template> "Title" --field …` | Create a page from a template (`akit new <template> --help` shows fields + rules) |
| `akit set <page> field=value` / `akit ls <template> --where …` | Change and query template fields |
| `akit template ls` / `akit template new <name> --from <page>` | List templates / turn a page shape into one |
| `akit index` / `akit check` / `akit log` | Catalog, lint, and log the wiki |
| `akit bookmark add/ls/rm/sync` | Manage bookmark skills |
| `akit adapters` | Show supported agents and the judge in use |
| `akit config share` / `akit lock` | Show the owner-only share setting / re-apply its locks |
| `akit kit ls` / `akit install <page>` | Browse and install kit pages |
| `akit sync [--take … \| --take-safe] [--done]` | Review and take upstream kit changes |
| `akit share <targets>` / `akit share submit` | Propose content back to the kit as a PR |

## Develop

```bash
uv run akit --help
uv run python -m unittest discover -s tests
uv run akit check
```
