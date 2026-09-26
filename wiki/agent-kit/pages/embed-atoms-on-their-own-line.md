---
id: ed714f52-5608-4aa5-8ed7-cd0450430339
title: Embed atoms on their own line
---

Embed an atom with Obsidian syntax on a line by itself:

```markdown
## Test doubles
![[prefer-fakes-over-mocks]]
![[test-the-real-class|Test the real class]]
```

The name is the atom's file name (unique across the wiki). Use `path/from/wiki/name` only to
disambiguate. Inline `[[links]]` in prose are plain links, not embeds. Atoms can be embedded in
more than one page; there is still exactly one file.
