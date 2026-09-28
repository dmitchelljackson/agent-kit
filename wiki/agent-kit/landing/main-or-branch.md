---
id: d5a5d2a2-b3af-46b6-91d1-4bcde675703e
title: main or branch
---

Ask: is this true no matter which branch you're on?

- **Yes: `main`.** Tickets, coding rules, conventions, decisions already made, ingested sources. Everyone
  needs them current, now.
- **No: `branch`.** It only becomes true when this branch's work merges: the feature being built, its BDD
  changes, setup for what you're building. It merges with that work.

The wiki root defaults to `branch`, the safe choice. Templates declare their scope (ticket and source:
main; bdd, setup, tool: branch), and `akit new` writes it on the directory the first time.
