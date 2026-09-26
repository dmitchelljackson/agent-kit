---
id: 963f81a9-9b7d-47c6-a3f5-40a8d41e6f5b
title: How to add a bookmark
---

1. Make sure the page exists and actually contains what the moment needs.
2. `akit bookmark add <page> --when "Use before ..." --evidence "<the mistake or near-miss>"`
3. akit runs the bookmark judge in a fresh context. If no judge agent is configured, it writes a packet
   file: hand it to a fresh subagent, then re-run with `--verdict "<its VERDICT line>"`.
4. On approval akit writes the field, regenerates the skills, and logs it.

New skills may not load until the next session; read the page directly for the rest of this one.
