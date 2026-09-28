---
id: a80269b9-c04e-4b61-9556-0427efdff474
title: Scope is set by directory
---

A `.akit-scope` file holds one word, `main` or `branch`, and applies to its directory and everything
below it; the nearest one wins. There are no per-file exceptions: if a file needs a different scope, it
belongs in a different directory. `akit scope` lists scope files; `akit scope <path>` shows a path's scope
and which file set it. `akit read` shows each page's and atom's scope in its tag.
Why: deciding where things live and where they land is the same decision.
