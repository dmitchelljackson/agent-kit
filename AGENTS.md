# agent-kit

This repo is two things:

1. **`akit`**, a dependency-free Python CLI (`src/agent_kit/`) for an atom-based, git-backed wiki:
   pages, atoms, bookmarks (generated skills), judges, install/sync/share.
2. **The kit's wiki** (`wiki/`): shared conventions, rules, reference, and tools that projects install.
   It uses the same format it defines.

`BOOTSTRAP.md` is what owners point agents at to set up a project. The PR template in `.github/`
is what `akit share` fills in.

## Commands

- Run the CLI from source: `uv run akit <command>`
- Tests: `uv run python -m unittest discover -s tests`
- Wiki lint: `uv run akit check` (must pass with 0 errors; CI runs it)

## Working on the wiki

Read `uv run akit read wiki/agent-kit` first. Create and restructure atoms only through
`akit atom ...`; edit atom content directly. Everything in `wiki/` is public and must be general:
no project names, private links, customers, or credentials.

## Working on the CLI

- No runtime dependencies. Python 3.10+ standard library only.
- Keep it small. Add a command only when agents keep getting something wrong by hand.
- Every change to wiki-editing behavior needs a test in `tests/`.
- Agent adapters (skills folders, headless judge commands) live in `src/agent_kit/adapters.json`.
  Mark a judge command `verified` only after running it against the real CLI.

## Never

- Push to `main` directly; open a PR.
- Commit secrets or project-specific content from other repos.
