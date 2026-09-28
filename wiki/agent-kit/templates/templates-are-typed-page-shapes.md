---
id: a782f98c-fbf5-4153-8520-173a23d7033a
title: Templates are typed page shapes
---

A template (`wiki/templates/<name>/`) defines fields (types, allowed values, required), rules (atoms on
its page), and an optional skeleton. Before creating a page of a known shape, run
`akit new <template> --help`: it lists the fields and prints the rules. Create with
`akit new <template> "Title" --field value ...`, change fields with `akit set <page> field=value`, and
list with `akit ls <template> --where field=value`. `akit check` validates every templated page.
Each template also declares a scope (see Scope and landing). Templates are optional; a plain
`akit page new` is fine for one-off pages.
