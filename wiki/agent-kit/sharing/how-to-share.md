---
id: 901263f8-7f67-4389-ad77-7a269f4414a5
title: How to share
---

1. Make the content general: no project names, domains, internal URLs, people, or business details.
2. `akit share <page|atom> ... --evidence "<why it's general; what went wrong>"`
   akit scans for secrets and project terms, runs the share judge (or `--owner`), and prepares a branch
   of the kit with your atoms copied in, renaming files if names collide.
3. Fill every `TODO(akit)` in the PR body file it prints.
4. `akit share submit --title "<title>"` commits, pushes (forking if you can't push), and opens the PR.
The kit owner reviews and merges. Other projects get it on their next `akit sync`.
