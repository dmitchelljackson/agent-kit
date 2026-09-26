---
id: e1bea945-2245-4ed0-850e-4387c36fca80
title: Read pages with akit read
---

`akit read <page>` prints the page with every embed replaced by the atom's title and body, each
tagged with its id and path, in one call. Always read pages this way rather than opening `_page.md`,
which only shows the embed lines. `akit read` fails loudly on a missing atom instead of skipping it.
Humans can read the same pages rendered in Obsidian (open the `wiki/` folder as a vault).
