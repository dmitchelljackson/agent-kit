---
id: 80741b32-6142-4961-b3e7-8b11bbc70ea8
title: "Sharing is the owner's call"
---

`.agent-kit-owner.json` records the owner's decisions. `share` says whether this project may share to the public kit:
**off** (never: private, client, or employer code), **owner** (only when the owner explicitly asks,
with `--owner`), or **on** (agents may propose; a judge gates each share). A missing file means off.

akit creates it once, during `akit init`, from the owner's answer, then locks it: read-only, plus
deny rules for agents that support them. The owner can hard-lock it with the command `akit init` prints.
Never edit, unlock, chmod, or work around it. When `akit share` refuses, tell the owner and give them the
file link it prints; they change it by hand if the project is no longer private.
Why: a private project leaking into a public repo can't be undone.
