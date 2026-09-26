---
id: 74d43c31-6e74-4d6f-a46c-9c35ad51af5c
title: Atom file format
---

An atom is `<readable-name>.md` in its page's folder:

```markdown
---
id: 3f8e2a1c-9b4d-4e7f-a2c6-1d5b8e9f0a3c
title: Prefer fakes over mocks
status: locked        # optional; decisions only: locked | derived | open | later
---
Body in plain markdown. Rules end with a "Why:" line.
```

The `id` is the atom's permanent identity: sync, sharing, and PRs match atoms by it.
The filename is for humans and embeds; it can change, the id never does.
File names are unique across the whole wiki so bare embeds are never ambiguous.
