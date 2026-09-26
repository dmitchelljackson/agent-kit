---
id: b3c03ea6-b7f0-4c30-b6ab-5ce288e565c4
title: How judges run
---

A judge is an agent in a fresh context that sees only the criteria, the candidate, and minimal context,
never the proposing agent's reasoning. akit runs it through a headless agent (see `akit adapters`):
`--judge`, then `AKIT_JUDGE`, then `judge` in config, then the first project agent with a judge command.
With none available, akit writes a packet file for a subagent. The owner can always override.
