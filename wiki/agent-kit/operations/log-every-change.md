---
id: 19c3cd07-949f-4d39-a7d4-25a4062da081
title: Log every change
---

`wiki/log.md` is append-only and chronological. Add entries with `akit log <op> "<subject>"`, using
ops like `ingest`, `decision`, `update`, `lint`, `bookmark`, `install`, `sync`, `share`. akit logs its
own structural commands. `log.md` merges with `merge=union` so parallel branches don't conflict.
