---
id: ed56f6ac-bfa0-48ef-a79e-3e2c87a10828
title: Never put secrets in the wiki
---

Name the values (e.g. `FIREBASE_API_KEY`), never their contents. Record where the secret is stored in `secrets_location` (a password manager item, an uncommitted `.env`). Never ask for passwords or 2FA codes in chat.
