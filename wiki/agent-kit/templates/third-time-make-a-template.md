---
id: d299e44f-51f5-4b22-9904-676a56cf1e9b
title: Third time, make a template
---

When you've written the same shape of page three times, or you're about to create a series, stop and
make a template: `akit template new <name> --from <best example page>`, then give its fields real types
and write its rules as atoms. Then bring the existing pages up to spec in the same change: add
`template: <name>`, fill required fields, restructure to match, and run `akit check` until it's clean.
Log it (`akit log template "<name>"`).
Why: repeated shapes without a template drift apart, and structured fields are what make pages queryable.
