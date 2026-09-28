---
id: 6c902cac-f2e9-41ec-8ea2-49c8ca1aa5be
title: "Landing modes are the owner's call"
---

`landing` in `.agent-kit-owner.json` (owner-only, locked like `share`; `akit config` shows it):

- **open**: no scoping. `akit land` lands every wiki change. Good for solo projects on main.
- **scoped**: `akit land` lands only main-scoped directories; branch-scoped pages ride with the branch.
- **pr**: like scoped, but through one rolling PR (`akit/wiki-updates`) instead of straight to main.
  For teams or protected main. `scoped` falls back to this automatically if main rejects a push.

This only governs wiki changes agents land. What happens to code is always the owner's call.
