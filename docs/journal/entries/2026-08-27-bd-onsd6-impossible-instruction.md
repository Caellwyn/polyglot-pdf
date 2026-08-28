---
date: 2026-08-27
bead: polyglot-pdf-onsd6
title: "fix(scripts): an operator message that told you to do something impossible"
tags: [scripts, review]
---

## Trigger

`bootstrap_editor_user.py` printed *"They must sign in once before a role can
be granted"* when the email had no Firebase account. I wrote that during bd
`polyglot-pdf-hn0jq`. The hosted editor's gate is a free-text access code
(`AccessCodeGate.tsx`), not a Firebase sign-in, so a brand-new person cannot
create an account by trying to use the editor. Building that sign-in is bd
`polyglot-pdf-yswp3`, still open.

## Scar tissue

**An instruction that cannot be followed is worse than no instruction.** A
missing message sends the operator to the docs; a confident wrong one sends
them to wait for an event that will never happen. This one named the exact
thing the epic had not built yet.

**The same sentence was TRUE in the sibling script.** `bootstrap_voice_dev.py`
says "sign in once" and should: the voice app has real sign-up
(`AuthContext.tsx` -- `createUserWithEmailAndPassword` / `signInWithPopup`).
Identical words, different truth, because the two surfaces have different
capabilities. A repo-wide search-and-replace "fixing" both would have broken a
correct message -- so a test records why they differ.

**Pin a message with an ALLOWLIST plus a residue check, never a banned word.**
Banning "sign in" is one synonym from defeat, and it would also flag a correct
future message that says "...once yswp3 ships sign-in". So: the message must
name a remedy that EXISTS (Firebase console / Admin SDK / gcloud), AND must
not still promise the sign-in flow. Verified that either alone is
insufficient -- a message naming the console while still saying "they must
sign in" passes the allowlist and fails only the residue check.

**My extractor grabbed the wrong message first.** It took the last
`unknown_email` match, which is the REVOKE path -- that one legitimately needs
no remedy, since the person already has an account. It anchors on the grant
call now. And the bead's own single-line grep had missed the string entirely,
because it wraps across two lines: the same trap that hid a call site in bd
`5tuas` earlier the same day.
