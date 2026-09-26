---
id: 0bdba297-778b-493b-aed6-e1f69b996a1b
title: Installing and syncing
---

- `akit kit ls` lists pages available in the kit (✓ = installed).
- `akit install <page> [-r]` copies a page (and its parents) into the project.
- `akit sync` reports what changed upstream since the recorded commit: safe updates, conflicts,
  new atoms on pages you have, removals, and new pages.
- `akit sync --take <id|page> ...` or `--take-safe` applies what the owner chose.
- `akit sync --done` records the new kit commit. Anything not taken simply stays different.
