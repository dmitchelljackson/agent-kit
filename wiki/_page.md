---
title: agent-kit wiki
---

Shared knowledge for every project that uses agent-kit: conventions, rules, reference, and tools.
Projects install the pages they need with `akit install <page>`, and send improvements back with `akit share`.
The full catalog is [index.md](index.md); the history is [log.md](log.md).

## How to read decisions

Atoms that record decisions carry a `status`:

- **LOCKED** — agreed by the owner. Implement as written unless superseded.
- **DERIVED** — an engineering interpretation needed to implement locked behavior.
- **OPEN** — unresolved. Don't invent behavior that materially changes the product.
- **LATER** — explicitly deferred.

When a newer decision supersedes an older one, update the atom and log it. Never leave two
contradictory "current" answers in the wiki.
