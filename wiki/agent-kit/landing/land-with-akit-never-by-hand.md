---
id: a3c2d285-e979-4791-b351-163cda40f1ad
title: Land with akit, never by hand
---

After changing main-scoped pages (a ticket's status, a new rule), run `akit land` before you finish.
Check first with `akit land --dry-run`. Never commit or push wiki changes to main yourself.

`akit land` builds the commit in a temporary worktree from main's tip, so your branch, your checkout, and
any code are never touched. It appends new log entries and rebuilds the index and bookmark skills on main,
retries if main moved, and never pushes commits of the owner's that aren't pushed yet (on a main with
unpushed commits it commits locally and stops). Naming a branch-scoped path fails; there is no force.
The landed files stay modified on your branch, identical to main, so they merge cleanly.
