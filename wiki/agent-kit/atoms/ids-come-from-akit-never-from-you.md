---
id: 2dbad093-e4eb-41b2-99ba-34791e1ab08b
title: IDs come from akit, never from you
---

Never type or invent an atom ID. `akit atom new` generates a UUID from the OS random source.
When you need to reference an existing atom's ID, copy it from `akit atom find`, the file, or
`akit read` output; never retype it from memory.
Why: models mangle long random strings and can't produce real randomness; one typo silently breaks identity.
