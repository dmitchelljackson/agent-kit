---
id: 8bf5c63b-b557-4957-9072-11e4d6f07929
title: Adding or fixing an agent
---

Override or add an agent under `"adapters"` in `.agent-kit.json` (per project) or
`~/.config/akit/config.json` (per user), e.g.

```json
{"adapters": {"grok": {"skills_dir": ".grok/skills", "judge": "grok -p \"$(cat {file})\""}}}
```

`{file}` is replaced by the judge packet path; without it the packet is piped on stdin.
Once a command is confirmed against the real CLI, share the fix to the kit's built-in registry.
