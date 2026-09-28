---
id: 8507a9d9-8bbe-403c-9fbd-3fdb04de28d5
title: Scope changes ride with the branch
---

Landing uses main's scope files. Editing or deleting a `.akit-scope` file only takes effect for landing
once it merges, so a directory can't quietly become main-pushable. The one exception: a new scope file for
a directory main doesn't have yet (like the first `tickets/`) counts right away and lands with it.
