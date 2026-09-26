---
id: d6295631-620e-435a-bb71-78d954ba06cd
title: Projects own their copies
---

Installed pages are plain files in the project; the only link to the kit is the commit recorded in
`.agent-kit.json`. Nothing syncs automatically. A project can differ from the kit on any atom, and
that's fine: sync never overwrites local changes without asking.
