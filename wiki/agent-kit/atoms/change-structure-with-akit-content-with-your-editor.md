---
id: 554db5f2-ace5-4fc7-8c67-d99788d44567
title: Change structure with akit, content with your editor
---

Structure goes through the CLI so IDs and embeds stay consistent:

- `akit atom new "Title" --page <page> [--body ...] [--status ...] [--after <atom>]`
- `akit atom rename <id|name> "New title"` (renames the file and rewrites every embed)
- `akit atom move <id|name> --page <page>`
- `akit atom rm <id|name>`

Edit an atom's body (and title line, if you're not renaming) directly in its file.
Never `mv` or delete atom files by hand. `akit check` catches broken embeds if something slips.
