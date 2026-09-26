<!-- akit:begin — managed by `akit init`; edit outside this block -->
## Knowledge

Project knowledge lives in `{{WIKI}}/`, a tree of pages built from atoms. Start from `{{WIKI}}/index.md`.
Read a page with `akit read <page>`; it assembles the page with every atom inlined.
Sources you were given (docs, specs, exports, transcripts) go in `raw/` and are never edited.

When your work locks a decision, changes behavior, or teaches you something future work
needs, update the wiki in the same change and log it with `akit log <op> "<subject>"`.
Create and restructure atoms only through `akit atom ...` (it generates IDs and keeps
embeds intact); edit atom content directly in the file. Full conventions: `akit read {{WIKI}}/agent-kit`.

### Bookmarks

Bookmarks are skills that point into the wiki. Each fires at a specific moment
("Use before writing Kotlin unit tests") and tells you which page to read first.
They hold no rules; the wiki is the only source of truth. Before starting work in a
new area, check your skills for a matching bookmark.

Create one (`akit bookmark add`) only when a page must be read at a recognizable
moment and skipping it caused a mistake, or plausibly would. If a page would help
any project on this stack, propose it upstream with `akit share`. Both run an
independent judge unless the owner explicitly asked for it (`--owner`).
<!-- akit:end -->
