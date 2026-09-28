<!-- akit:begin — managed by `akit init`; edit outside this block -->
## Knowledge

Project knowledge lives in `{{WIKI}}/`, a tree of pages built from atoms. Start from `{{WIKI}}/index.md`.
Read a page with `akit read <page>`; it assembles the page with every atom inlined.
Sources you were given (docs, specs, exports, transcripts) go in `raw/` and are never edited;
each gets a page in `{{WIKI}}/sources/` (`akit new source`).

When your work locks a decision, changes behavior, or teaches you something future work
needs, update the wiki in the same change and log it with `akit log <op> "<subject>"`.
Create and restructure atoms only through `akit atom ...` (it generates IDs and keeps
embeds intact); edit atom content directly in the file. Full conventions: `akit read {{WIKI}}/agent-kit`.

Don't repeat yourself: every fact lives in one atom; embed or link it, never copy it. Before making a
page of a known shape, check `akit new --help` and use the template (its `--help` prints the fields and
rules). When you've written the same shape of page three times, make a template
(`akit template new <name> --from <page>`) and bring the existing pages up to spec in the same change.

### Getting wiki changes onto main

Every wiki directory is scoped by its nearest `.akit-scope`: `main` (true regardless of branch:
tickets, rules, decisions, sources) or `branch` (true once this branch's work merges: the feature being
built). Put pages in the directory whose scope fits; `akit scope` shows them. After changing main-scoped
pages, run `akit land` (check with `--dry-run`) before you finish. Never commit or push wiki changes to
main yourself; `akit land` does it without touching code or your branch. Branch-scoped pages are
committed with the branch's work like any other file.

### Bookmarks

Bookmarks are skills that point into the wiki. Each fires at a specific moment
("Use before writing Kotlin unit tests") and tells you which page to read first.
They hold no rules; the wiki is the only source of truth. Before starting work in a
new area, check your skills for a matching bookmark.

Create one (`akit bookmark add`) only when a page must be read at a recognizable
moment and skipping it caused a mistake, or plausibly would. It runs an independent
judge unless the owner explicitly asked for it (`--owner`).

### Owner settings

`.agent-kit-owner.json` holds the owner's decisions (`akit config` shows them):
`share` (may content go to the public kit: **off**, **owner** only when they ask with `--owner`, or
**on** with a judge gating each share) and `landing` (**open**: every wiki change may land on main;
**scoped**: only main-scoped directories; **pr**: through one rolling PR). Never edit, unlock, chmod, or
work around that file or the permission rules protecting it. If akit refuses something because of
it and the owner wants it changed, tell them and give them the file link akit prints.
<!-- akit:end -->
