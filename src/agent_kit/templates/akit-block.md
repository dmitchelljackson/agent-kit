<!-- akit:begin — managed by `akit init`; edit outside this block -->
## Knowledge

Project knowledge lives in `{{WIKI}}/`, a tree of pages built from atoms. Start from `{{WIKI}}/index.md`.
Read a page with `akit read <page>`; it assembles the page with every atom inlined.
Sources you were given (docs, specs, exports, transcripts) go in `raw/` and are never edited.

When your work locks a decision, changes behavior, or teaches you something future work
needs, update the wiki in the same change and log it with `akit log <op> "<subject>"`.
Create and restructure atoms only through `akit atom ...` (it generates IDs and keeps
embeds intact); edit atom content directly in the file. Full conventions: `akit read {{WIKI}}/agent-kit`.

Don't repeat yourself: every fact lives in one atom; embed or link it, never copy it. Before making a
page of a known shape, check `akit new --help` and use the template (its `--help` prints the fields and
rules). When you've written the same shape of page three times, make a template
(`akit template new <name> --from <page>`) and bring the existing pages up to spec in the same change.

### Bookmarks

Bookmarks are skills that point into the wiki. Each fires at a specific moment
("Use before writing Kotlin unit tests") and tells you which page to read first.
They hold no rules; the wiki is the only source of truth. Before starting work in a
new area, check your skills for a matching bookmark.

Create one (`akit bookmark add`) only when a page must be read at a recognizable
moment and skipping it caused a mistake, or plausibly would. It runs an independent
judge unless the owner explicitly asked for it (`--owner`).

### Sharing to the kit

Whether content from this project may go to the public kit is the owner's call, recorded in
`.agent-kit-share.json` (`akit config share` shows it): **off** (never), **owner** (only when the
owner explicitly asks, with `--owner`), or **on** (agents may propose; a judge gates each share).
Never edit, unlock, chmod, or work around that file or the permission rules protecting it. If
`akit share` is refused and the owner wants to share, tell them and give them the file link it prints.
<!-- akit:end -->
